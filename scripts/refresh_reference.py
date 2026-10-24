"""Regenerate API, tool and configuration reference files from current source.

Requires the project's dev dependencies. Does not open runtime data or call models.
"""

import ast
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
sys.path.insert(0, str(ROOT))

from gramem.config import Config  # noqa: E402


def write_json(name, value):
    (DOCS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    source = ROOT / 'integrations/control-panel/dashboard/api.py'
    spec = importlib.util.spec_from_file_location('gramem_dashboard_contract', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI(
        title='GraMem control-panel plugin router',
        version='1.8.1',
        description=(
            'Source-generated plugin contract. Hosted by Hermes: administrator '
            'authentication and profile query resolution are supplied by the host, '
            'not this router. See control-panel.md for deployment semantics.'
        ),
    )
    app.include_router(module.router, prefix='/api/plugins/hermes-control')
    write_json('openapi.json', app.openapi())

    tree = ast.parse((ROOT / 'gramem/hermes.py').read_text())
    provider = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                    and node.name == 'GraMemProvider')
    method = next(node for node in provider.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'get_tool_schemas')
    schemas = ast.literal_eval(method.body[0].value)
    write_json('tool-schemas.json', schemas)
    write_json('config-defaults.json', asdict(Config()))

    lines = [
        '# 接口契约索引', '',
        '核对日期：2026-10-14。此页及 JSON 契约由当前源码生成；操作说明见'
        '[接口手册](interfaces.md)和[管理员 REST](control-panel.md)。', '',
        '## 模型工具', '',
        '[tool-schemas.json](tool-schemas.json)包含五个工具的完整 JSON Schema。'
        '身份由宿主解析，不能传入任意 principal；参数/分页语义与手册共同维护。', '',
        '| 工具 | 必填 | 参数 |', '|---|---|---|',
    ]
    for schema in schemas:
        params = schema['parameters']
        lines.append(
            '| `' + schema['name'] + '` | ' + ', '.join(params.get('required', []))
            + ' | ' + ', '.join(params['properties']) + ' |'
        )
    lines.extend([
        '', '## REST 路由', '',
        '[openapi.json](openapi.json)记录插件路由参数、请求体及校验约束。'
        '宿主的认证/profile 中间件不在插件规范中；所有请求仍需管理员认证，'
        '并指定已有 profile，不能据此推断匿名入口。', '',
        '成功响应主要是动态字典，未声明完整 response_model；OpenAPI 不能替代'
        '[响应与错误手册](control-panel.md)。', '',
        '| 方法 | 路径 | 源码函数 |', '|---|---|---|',
    ])
    for route in module.router.routes:
        for method in sorted(route.methods):
            lines.append(f'| {method} | `{route.path}` | `{route.endpoint.__name__}` |')
    lines.extend([
        '', '## 配置与更新', '',
        '[config-defaults.json](config-defaults.json)包含全部 Config 默认字段；'
        '实例显式值在[配置手册](configuration.md)与实例当前状态维护。', '',
        '修改工具/路由/配置后运行 `python scripts/refresh_reference.py`，'
        '同步参数、响应、权限和使用说明。契约是源码快照，不是实时运行状态；'
        '生成过程不打开记忆库、不调用模型。', '',
    ])
    (DOCS / 'api-reference.md').write_text('\n'.join(lines))
    print(json.dumps({
        'tool_schemas': len(schemas),
        'rest_operations': sum(len(route.methods) for route in module.router.routes),
        'configuration_fields': len(asdict(Config())),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
