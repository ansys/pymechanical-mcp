# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Object discovery, property change previews, and script checks.

The Mechanical-side scripts here inspect the connected session itself, so the
results always match the connected release instead of a bundled API snapshot.
They run in the Mechanical scripting engine, which is IronPython 2.7 for remote
sessions, so they avoid f-strings and annotations. Tool arguments reach them as
a base64-encoded JSON payload, which cannot break out of the script text.
"""

import ast
import base64
import difflib
import json
import secrets
import time
from typing import Any

from ansys.mechanical.mcp.errors import InvalidArgumentsError, StalePreviewError

#: Seconds a property change preview stays valid.
PREVIEW_TTL_SECONDS = 600

#: Maximum number of pending previews kept per server.
MAX_PENDING_PREVIEWS = 100

#: Maximum number of distinct API name chains checked per script.
MAX_CHECKED_CHAINS = 300

# Python 3 functions that are statements in the IronPython 2.7 engine. They are
# not looked up as names, because they are not names in that engine.
_STATEMENT_NAMES = frozenset({"print", "exec"})

_HELPERS = r"""
import base64
import json
import sys

import clr
import System

try:
    _mcp_text = (basestring,)
except NameError:
    _mcp_text = (str,)
# In IronPython 2.7, str() raises for .NET text with non-ASCII characters, such
# as an object named with an umlaut, and so does unicode() called through an
# alias. .NET strings already arrive as text, so keep them as they are.
def _mcp_str(value):
    if isinstance(value, _mcp_text):
        return value
    return u'{0}'.format(value)
try:
    _mcp_ints = (int, long)
except NameError:
    _mcp_ints = (int,)

_MCP_INT_RANGES = {
    'System.Byte': (0, 255),
    'System.SByte': (-128, 127),
    'System.Int16': (-32768, 32767),
    'System.UInt16': (0, 65535),
    'System.Int32': (-2147483648, 2147483647),
    'System.UInt32': (0, 4294967295),
    'System.Int64': (-9223372036854775808, 9223372036854775807),
    'System.UInt64': (0, 18446744073709551615),
}
_MCP_FLOAT_TYPES = ('System.Double', 'System.Single')
_MCP_EDITABLE_KINDS = ('bool', 'int', 'float', 'string', 'enum', 'quantity')
_MCP_DATA_MODEL_OBJECT = clr.GetClrType(Ansys.Mechanical.DataModel.Interfaces.IDataModelObject)
_MCP_FLAGS = clr.GetClrType(System.FlagsAttribute)
_MCP_OBSOLETE = clr.GetClrType(System.ObsoleteAttribute)


def _mcp_payload(text):
    return json.loads(base64.b64decode(text).decode('utf-8'))


def _mcp_error(code, message, details=None):
    return {'success': False, 'error_code': code, 'error': message, 'details': details or {}}


def _mcp_context():
    try:
        import platform
        engine = platform.python_implementation()
    except Exception:
        engine = 'IronPython' if 'IronPython' in sys.version else 'Python'
    try:
        version = str(ExtAPI.DataModel.Project.ProductVersion)
    except Exception:
        version = None
    return {
        'product_version': version,
        'python_engine': '{0} {1}.{2}.{3}'.format(engine, *tuple(sys.version_info[:3])),
    }


def _mcp_type_name(clr_type):
    try:
        if clr_type.IsGenericType:
            arguments = ', '.join([_mcp_type_name(a) for a in clr_type.GetGenericArguments()])
            return clr_type.Name.split('`')[0] + '[' + arguments + ']'
        return str(clr_type.Name)
    except Exception:
        return str(clr_type)


def _mcp_kind(property_type):
    # Classify by the declared .NET type, so values are never read to decide.
    underlying = System.Nullable.GetUnderlyingType(property_type)
    clr_type = property_type if underlying is None else underlying
    name = clr_type.FullName or clr_type.Name
    if name == 'System.Boolean':
        kind = 'bool'
    elif name in _MCP_INT_RANGES:
        kind = 'int'
    elif name in _MCP_FLOAT_TYPES:
        kind = 'float'
    elif name == 'System.String':
        kind = 'string'
    elif clr_type.IsEnum:
        kind = 'enum'
    elif name == 'Ansys.Core.Units.Quantity':
        kind = 'quantity'
    elif _MCP_DATA_MODEL_OBJECT.IsAssignableFrom(clr_type):
        kind = 'object'
    else:
        kind = 'other'
    return clr_type, kind, underlying is not None


def _mcp_number(value):
    value = float(value)
    if value != value or value in (float('inf'), float('-inf')):
        return str(value)
    return value


def _mcp_summary(obj):
    entry = {}
    for key, read in (
        ('object_id', lambda o: int(o.ObjectId)),
        ('name', lambda o: _mcp_str(o.Name)),
        ('category', lambda o: str(o.DataModelObjectCategory)),
        ('state', lambda o: str(o.ObjectState)),
    ):
        try:
            entry[key] = read(obj)
        except Exception:
            entry[key] = None
    return entry


def _mcp_value(value, kind):
    if value is None:
        return None
    if kind == 'bool':
        return bool(value)
    if kind == 'int':
        return int(value)
    if kind == 'float':
        return _mcp_number(value)
    if kind == 'string':
        return value if isinstance(value, _mcp_text) else _mcp_str(value)
    if kind == 'enum':
        return str(value)
    if kind == 'quantity':
        return {'value': _mcp_number(value.Value), 'unit': _mcp_str(value.Unit)}
    if kind == 'object':
        return _mcp_summary(value)
    return None


def _mcp_is_flags(clr_type):
    return len(clr_type.GetCustomAttributes(_MCP_FLAGS, False)) > 0


def _mcp_properties(obj):
    # Public, non-indexed API properties by name. Reflection can list a name
    # twice (an override and its base), so only the first is kept.
    found = {}
    for info in obj.GetType().GetProperties():
        if info.Name in found or info.Name == 'InternalObject':
            continue
        if info.GetIndexParameters().Length:
            continue
        found[info.Name] = info
    return found


def _mcp_writable(info):
    return bool(info.CanWrite and info.GetSetMethod() is not None)
"""

_FIND_OBJECTS = r"""

def _mcp_find_objects(args):
    parent_id = args.get('parent_id')
    if parent_id is None:
        root = ExtAPI.DataModel.Project
    else:
        root = DataModel.GetObjectById(parent_id)
        if root is None:
            return _mcp_error('not_found', 'No object has ID {0}.'.format(parent_id))
    category = args.get('category')
    if category:
        names = list(System.Enum.GetNames(clr.GetClrType(DataModelObjectCategory)))
        lookup = dict((n.lower(), n) for n in names)
        if category.lower() not in lookup:
            return _mcp_error(
                'invalid_arguments',
                'Unknown object category {0}.'.format(category),
                {'candidates': names},
            )
        category = lookup[category.lower()]
    needle = (args.get('name_contains') or '').lower()
    max_depth = args.get('max_depth')
    limit = args['limit']
    matches = []
    total = 0
    counts = {}
    stack = [(root, 0, None)]
    while stack:
        obj, depth, parent_path = stack.pop()
        entry = _mcp_summary(obj)
        name = entry['name'] or ''
        path = name if parent_path is None else parent_path + ' > ' + name
        key = str(entry['category'])
        counts[key] = counts.get(key, 0) + 1
        try:
            children = list(obj.Children)
        except Exception:
            children = []
        if (not category or entry['category'] == category) and (
            not needle or needle in name.lower()
        ):
            total += 1
            if len(matches) < limit:
                entry['path'] = path
                entry['depth'] = depth
                entry['child_count'] = len(children)
                matches.append(entry)
        if max_depth is None or depth < max_depth:
            for child in reversed(children):
                stack.append((child, depth + 1, path))
    result = {
        'success': True,
        'root': _mcp_summary(root),
        'match_count': total,
        'returned_count': len(matches),
        'truncated': total > len(matches),
        'objects': matches,
        'category_counts': counts,
    }
    result.update(_mcp_context())
    return result
"""

_DESCRIBE_OBJECT = r"""

def _mcp_describe_object(args):
    obj = DataModel.GetObjectById(args['object_id'])
    if obj is None:
        return _mcp_error('not_found', 'No object has ID {0}.'.format(args['object_id']))
    reflected = _mcp_properties(obj)
    details = {}
    gui_only = []
    try:
        visible = list(obj.VisibleProperties)
    except Exception:
        visible = []
    for prop in visible:
        try:
            api_name = prop.APIName
            item = {
                'caption': _mcp_str(prop.Caption),
                'display': _mcp_str(prop.StringValue),
                'read_only': bool(prop.ReadOnly),
            }
        except Exception:
            continue
        if api_name and api_name in reflected:
            details.setdefault(api_name, item)
        else:
            item['api_name'] = api_name or None
            gui_only.append(item)

    names = sorted(reflected)
    if args['details_only']:
        names = [n for n in names if n in details]
    needle = (args.get('name_contains') or '').lower()
    if needle:
        names = [
            n for n in names
            if needle in n.lower() or needle in details.get(n, {}).get('caption', '').lower()
        ]
        gui_only = [g for g in gui_only if needle in g['caption'].lower()]

    properties = []
    for name in names:
        info = reflected[name]
        clr_type, kind, nullable = _mcp_kind(info.PropertyType)
        entry = {
            'name': name,
            'type': _mcp_type_name(clr_type),
            'kind': kind,
            'writable': _mcp_writable(info),
        }
        if nullable:
            entry['nullable'] = True
        try:
            if info.IsDefined(_MCP_OBSOLETE, True):
                entry['obsolete'] = True
        except Exception:
            pass
        detail = details.get(name)
        if detail is not None:
            entry['caption'] = detail['caption']
            entry['display'] = detail['display']
            entry['read_only_in_details'] = detail['read_only']
        flags = False
        if kind == 'enum':
            entry['enum_values'] = list(System.Enum.GetNames(clr_type))
            flags = _mcp_is_flags(clr_type)
            if flags:
                entry['flags'] = True
        elif kind == 'int':
            entry['range'] = list(_MCP_INT_RANGES[clr_type.FullName])
        # Only scalar values are read: collections, tables, and other complex
        # values can be expensive to build and are summarized by 'display'.
        if kind != 'other':
            try:
                entry['value'] = _mcp_value(getattr(obj, name), kind)
            except Exception as exc:
                entry['value_error'] = _mcp_str(exc)[:300]
        entry['editable'] = bool(
            entry['writable']
            and kind in _MCP_EDITABLE_KINDS
            and not flags
            and not entry.get('read_only_in_details', False)
        )
        properties.append(entry)

    result = {'success': True, 'object': _mcp_summary(obj)}
    try:
        result['object']['parent_id'] = int(obj.Parent.ObjectId)
    except Exception:
        result['object']['parent_id'] = None
    result['object']['api_type'] = str(obj.GetType().FullName)
    try:
        result['unit_system'] = str(ExtAPI.Application.ActiveUnitSystem)
    except Exception:
        result['unit_system'] = None
    result['property_count'] = len(properties)
    result['properties'] = properties
    result['details_without_api'] = gui_only
    if args['include_methods']:
        ignored = ('CreateObjRef', 'GetLifetimeService', 'InitializeLifetimeService',
                   'Equals', 'GetHashCode', 'GetType', 'ToString')
        signatures = set()
        for method in obj.GetType().GetMethods():
            if method.IsSpecialName or not method.IsPublic or method.Name in ignored:
                continue
            parameters = ', '.join([
                _mcp_type_name(p.ParameterType) + ' ' + str(p.Name) for p in method.GetParameters()
            ])
            signatures.add('{0}({1}) -> {2}'.format(
                method.Name, parameters, _mcp_type_name(method.ReturnType)))
        result['methods'] = sorted(signatures)
    result.update(_mcp_context())
    return result
"""

_PROPERTY_CHANGE = r"""

def _mcp_convert(value, clr_type, kind, current):
    # Return (proposed, assignable, error). Types are checked strictly, because
    # the engine would silently coerce, for example, the string "yes" to True.
    if kind == 'bool':
        if not isinstance(value, bool):
            return None, None, 'This property expects true or false.'
        return value, value, None
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, _mcp_ints):
            return None, None, 'This property expects an integer.'
        low, high = _MCP_INT_RANGES[clr_type.FullName]
        if value < low or value > high:
            return None, None, 'Value must be between {0} and {1}.'.format(low, high)
        return value, value, None
    if kind == 'float':
        if isinstance(value, bool) or not isinstance(value, _mcp_ints + (float,)):
            return None, None, 'This property expects a number.'
        number = float(value)
        if number != number or number in (float('inf'), float('-inf')):
            return None, None, 'Value must be a finite number.'
        return number, number, None
    if kind == 'string':
        if not isinstance(value, _mcp_text):
            return None, None, 'This property expects a string.'
        return value, value, None
    if kind == 'enum':
        names = list(System.Enum.GetNames(clr_type))
        if _mcp_is_flags(clr_type):
            return None, None, 'Flag enums are not supported. Use run_python_script.'
        if not isinstance(value, _mcp_text) or value not in names:
            return None, None, 'Value must be one of: {0}.'.format(', '.join(names))
        return value, System.Enum.Parse(clr_type, value), None
    if kind == 'quantity':
        if not isinstance(value, _mcp_text):
            return None, None, 'This property expects a quantity string such as "10 [mm]".'
        try:
            quantity = Quantity(value)
        except Exception as exc:
            return None, None, 'Invalid quantity: {0}'.format(_mcp_str(exc))
        if current is None:
            return None, None, (
                'The current value is empty, so the unit cannot be validated. '
                'Use run_python_script.')
        try:
            converted = quantity.ConvertUnit(current.Unit)
        except Exception:
            return None, None, 'Unit [{0}] is not compatible with the current unit [{1}].'.format(
                _mcp_str(quantity.Unit), _mcp_str(current.Unit))
        proposed = {
            'value': _mcp_number(quantity.Value),
            'unit': _mcp_str(quantity.Unit),
            'in_current_unit': {
                'value': _mcp_number(converted.Value), 'unit': _mcp_str(converted.Unit)},
        }
        return proposed, quantity, None
    return None, None, (
        'Properties of type {0} cannot be changed with this tool. '
        'Use run_python_script.'.format(_mcp_type_name(clr_type)))


def _mcp_matches(kind, actual, proposed, assignable):
    if actual is None:
        return False
    if kind == 'quantity':
        try:
            value = float(actual.ConvertUnit(assignable.Unit).Value)
        except Exception:
            return False
        target = float(assignable.Value)
        return abs(value - target) <= 1e-9 * max(1.0, abs(target))
    if kind == 'float':
        return abs(float(actual) - proposed) <= 1e-12 * max(1.0, abs(proposed))
    return _mcp_value(actual, kind) == proposed


def _mcp_prepare_change(args):
    obj = DataModel.GetObjectById(args['object_id'])
    if obj is None:
        return None, _mcp_error('not_found', 'No object has ID {0}.'.format(args['object_id']))
    name = args['property_name']
    reflected = _mcp_properties(obj)
    info = reflected.get(name)
    if info is None:
        return None, _mcp_error(
            'invalid_arguments',
            'Object {0} has no API property {1}.'.format(args['object_id'], name),
            {'candidates': sorted(reflected)},
        )
    clr_type, kind, nullable = _mcp_kind(info.PropertyType)
    target = _mcp_summary(obj)
    target['property'] = name
    target['type'] = _mcp_type_name(clr_type)
    errors = []
    warnings = []
    read_only_in_details = False
    hidden_in_details = False
    try:
        detail = obj.PropertyByAPIName(name)
        if detail is not None:
            target['caption'] = _mcp_str(detail.Caption)
            read_only_in_details = bool(detail.ReadOnly)
            hidden_in_details = not bool(detail.Visible)
    except Exception:
        pass
    if not _mcp_writable(info):
        errors.append('{0} is read-only in the Mechanical API.'.format(name))
    elif read_only_in_details:
        errors.append(
            '{0} is read-only in the Details view for the current object state.'.format(name))
    elif hidden_in_details:
        warnings.append(
            '{0} is hidden in the Details view for the current object state, so Mechanical '
            'may not use the value.'.format(name))
    try:
        current_raw = getattr(obj, name)
    except Exception as exc:
        return None, _mcp_error(
            'upstream_error', 'Cannot read the current value: {0}'.format(_mcp_str(exc)))
    current = _mcp_value(current_raw, kind)
    proposed, assignable, problem = _mcp_convert(args['value'], clr_type, kind, current_raw)
    if problem:
        errors.append(problem)
    plan = {
        'obj': obj,
        'kind': kind,
        'current_raw': current_raw,
        'assignable': assignable,
        'target': target,
        'current': current,
        'proposed': proposed,
        'errors': errors,
        'warnings': warnings,
        'fingerprint': json.dumps([kind, current], sort_keys=True, ensure_ascii=False),
    }
    return plan, None


def _mcp_preview_change(args):
    plan, error = _mcp_prepare_change(args)
    if error is not None:
        return error
    valid = not plan['errors']
    result = {
        'success': True,
        'target': plan['target'],
        'current_value': plan['current'],
        'proposed_value': plan['proposed'],
        'validation': {'valid': valid, 'errors': plan['errors'], 'warnings': plan['warnings']},
        'fingerprint': plan['fingerprint'],
    }
    if valid:
        result['no_change'] = _mcp_matches(
            plan['kind'], plan['current_raw'], plan['proposed'], plan['assignable'])
    result.update(_mcp_context())
    return result


def _mcp_apply_change(args):
    plan, error = _mcp_prepare_change(args)
    if error is not None:
        return error
    if plan['errors']:
        return _mcp_error('validation_failed', ' '.join(plan['errors']),
                          {'current_value': plan['current']})
    if plan['fingerprint'] != args['fingerprint']:
        return _mcp_error(
            'stale_preview',
            'The current value changed after the preview. Preview the change again.',
            {'current_value': plan['current']},
        )
    try:
        setattr(plan['obj'], args['property_name'], plan['assignable'])
    except Exception as exc:
        return _mcp_error(
            'upstream_error', 'Mechanical rejected the value: {0}'.format(_mcp_str(exc)),
            {'current_value': plan['current']})
    try:
        after_raw = getattr(plan['obj'], args['property_name'])
        after = _mcp_value(after_raw, plan['kind'])
        matches = _mcp_matches(plan['kind'], after_raw, plan['proposed'], plan['assignable'])
    except Exception as exc:
        after = None
        matches = False
        plan['warnings'].append('Cannot read the value back: {0}'.format(_mcp_str(exc)))
    result = {
        'success': True,
        'target': plan['target'],
        'previous_value': plan['current'],
        'value': after,
        'readback_matches': matches,
        'warnings': plan['warnings'],
    }
    if not matches:
        result['warnings'].append(
            'Mechanical stored a different value than requested. Check the value above.')
    result.update(_mcp_context())
    return result
"""

_CHECK_SCRIPT = r"""

def _mcp_check_script(args):
    result = {'success': True}
    try:
        compile(args['source'], '<mcp-check>', 'exec')
        result['engine_syntax'] = {'valid': True}
    except SyntaxError as exc:
        result['engine_syntax'] = {
            'valid': False,
            'message': _mcp_str(exc.msg),
            'line': exc.lineno,
            'column': exc.offset,
            'text': (exc.text or '').rstrip(),
        }
    space = globals()
    builtins_obj = space.get('__builtins__')
    if isinstance(builtins_obj, dict):
        builtins_names = set(builtins_obj)
        read_builtin = builtins_obj.get
    else:
        builtins_names = set(dir(builtins_obj))
        read_builtin = lambda name: getattr(builtins_obj, name)
    resolutions = []
    for parts in args['chains']:
        root = parts[0]
        if root in space:
            obj = space[root]
        elif root in builtins_names:
            obj = read_builtin(root)
        else:
            resolutions.append({'status': 'undefined', 'index': 0})
            continue
        entry = {'status': 'ok'}
        for index in range(1, len(parts)):
            attribute = parts[index]
            try:
                members = dir(obj)
            except Exception:
                entry = {'status': 'unverified', 'index': index, 'reason': 'members unavailable'}
                break
            # hasattr only runs for names that dir() does not list, so it only
            # confirms dynamic attributes and never reads a listed property.
            if attribute not in members and not hasattr(obj, attribute):
                candidates = [m for m in members if not str(m).startswith('_')][:2000]
                entry = {'status': 'missing', 'index': index, 'candidates': candidates}
                break
            if index == len(parts) - 1:
                break
            # Properties are read to continue the chain. Methods are never called.
            try:
                obj = getattr(obj, attribute)
            except Exception as exc:
                entry = {'status': 'unverified', 'index': index, 'reason': _mcp_str(exc)[:200]}
                break
            if obj is None:
                entry = {'status': 'unverified', 'index': index, 'reason': 'value is None'}
                break
        resolutions.append(entry)
    result['resolutions'] = resolutions
    result.update(_mcp_context())
    return result
"""


def _encode(args: dict[str, Any]) -> str:
    """Encode tool arguments as base64 JSON, which is safe to embed in a script."""
    return base64.b64encode(json.dumps(args).encode("utf-8")).decode("ascii")


def _build(body: str, entry_point: str, args: dict[str, Any]) -> str:
    call = f'{entry_point}(_mcp_payload("{_encode(args)}"))'
    return f"{_HELPERS}{body}\njson.dumps({call}, ensure_ascii=False)\n"


def find_objects_script(args: dict[str, Any]) -> str:
    """Return the Mechanical script that searches the Outline tree."""
    return _build(_FIND_OBJECTS, "_mcp_find_objects", args)


def describe_object_script(args: dict[str, Any]) -> str:
    """Return the Mechanical script that describes one object."""
    return _build(_DESCRIBE_OBJECT, "_mcp_describe_object", args)


def preview_change_script(args: dict[str, Any]) -> str:
    """Return the Mechanical script that validates a property change without applying it."""
    return _build(_PROPERTY_CHANGE, "_mcp_preview_change", args)


def apply_change_script(args: dict[str, Any]) -> str:
    """Return the Mechanical script that applies a previewed property change."""
    return _build(_PROPERTY_CHANGE, "_mcp_apply_change", args)


def check_script_script(args: dict[str, Any]) -> str:
    """Return the Mechanical script that compiles a script and resolves its API names."""
    return _build(_CHECK_SCRIPT, "_mcp_check_script", args)


def close_matches(word: str, candidates: list[str], limit: int = 3) -> list[str]:
    """Return the candidates closest to ``word``, preferring a case-insensitive match."""
    names = [str(c) for c in candidates]
    exact = [c for c in names if c.lower() == word.lower()]
    similar = difflib.get_close_matches(word, names, n=limit, cutoff=0.6)
    return list(dict.fromkeys(exact + similar))[:limit]


def extract_api_chains(script: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    """Collect attribute chains rooted in names the script does not define itself.

    Parameters
    ----------
    script : str
        Script source.

    Returns
    -------
    tuple
        ``(chains, syntax_error, has_star_import)``. Each chain holds ``parts``
        (for example ``["Model", "Mesh", "ElementSize"]``), ``line``, and
        ``column``. ``syntax_error`` is set when the script is not valid Python 3,
        in which case no chains are returned.
    """
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return [], {"message": exc.msg, "line": exc.lineno, "column": exc.offset}, False

    bound: set[str] = set()
    star_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    star_import = True
                else:
                    bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)

    # Only the outermost node of each ``a.b.c`` chain starts a chain.
    inner = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, (ast.Attribute, ast.Name))
    }
    chains: dict[tuple[str, ...], dict[str, Any]] = {}
    for node in ast.walk(tree):
        if id(node) in inner or not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            continue
        if current.id in bound or current.id in _STATEMENT_NAMES:
            continue
        key = (current.id, *reversed(parts))
        if key not in chains:
            chains[key] = {"parts": list(key), "line": node.lineno, "column": node.col_offset + 1}
    ordered = sorted(chains.values(), key=lambda c: (c["line"], c["column"]))
    return ordered, None, star_import


def store_preview(
    store: dict[str, dict[str, Any]],
    mechanical: Any,
    object_id: int,
    property_name: str,
    value: Any,
    fingerprint: str,
) -> str:
    """Record a valid preview and return its single-use token."""
    now = time.monotonic()
    for token in [t for t, e in store.items() if now - e["issued"] > PREVIEW_TTL_SECONDS]:
        store.pop(token, None)
    while len(store) >= MAX_PENDING_PREVIEWS:
        store.pop(next(iter(store)))
    token = secrets.token_urlsafe(16)
    store[token] = {
        "session": id(mechanical),
        "object_id": object_id,
        "property_name": property_name,
        "value": json.dumps(value),
        "fingerprint": fingerprint,
        "issued": now,
    }
    return token


def take_preview(
    store: dict[str, dict[str, Any]],
    token: str,
    mechanical: Any,
    object_id: int,
    property_name: str,
    value: Any,
) -> dict[str, Any]:
    """Consume a preview token, checking that it matches this session and change.

    Raises
    ------
    StalePreviewError
        If the token is unknown, already used, expired, or from another session.
    InvalidArgumentsError
        If the token was issued for a different object, property, or value.
    """
    entry = store.pop(token, None)
    if entry is None:
        raise StalePreviewError(
            "Unknown or already used preview token. Call preview_property_change again."
        )
    if time.monotonic() - entry["issued"] > PREVIEW_TTL_SECONDS:
        raise StalePreviewError("The preview expired. Call preview_property_change again.")
    if entry["session"] != id(mechanical):
        raise StalePreviewError(
            "The preview was made for a different Mechanical session. "
            "Call preview_property_change again."
        )
    if (entry["object_id"], entry["property_name"], entry["value"]) != (
        object_id,
        property_name,
        json.dumps(value),
    ):
        raise InvalidArgumentsError(
            "The preview token was issued for a different object, property, or value. "
            "Pass the same arguments that were previewed."
        )
    return entry
