"""Read-only documentation and AST inspection."""
import ast
import os
import re
from pathlib import Path
from .phrases import BUSINESSCARDEXTRACTION, NOBUSINESSCARDEXTRACTION, GENERIC_NAMES


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(s) for s in sorted(phrases, key=lambda s: (-len(s), s))) + r')\b')


POSITIVE = pattern(BUSINESSCARDEXTRACTION)
NEGATIVE = pattern(NOBUSINESSCARDEXTRACTION)


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$', line):
                fence = None
            lines.append('')
        elif opening:
            fence = opening.group(1)
            lines.append('')
        else:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        paragraph = normalize(paragraph)
        negative |= bool(NEGATIVE.search(paragraph))
        positive |= bool(POSITIVE.search(NEGATIVE.sub(' ', paragraph)))
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    imports = {}
    modules = set()
    shadow = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or '')
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module or '') + '.' + alias.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadow.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.With, ast.AsyncWith)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else [i.optional_vars for i in node.items if i.optional_vars]
            for target in targets:
                shadow.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    def resolve(node):
        if isinstance(node, ast.Name):
            return '' if node.id in shadow else imports.get(node.id, '')
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''
    def allowed(func):
        return (isinstance(func, ast.Name) and func.id not in shadow) or (isinstance(func, ast.Attribute) and func.attr not in shadow and not (isinstance(func.value, ast.Name) and func.value.id in shadow and func.value.id in imports))
    calls = [n for n in nodes if isinstance(n, ast.Call) and allowed(n.func)]
    def gate(prefix):
        return any(m == prefix or m.startswith(prefix + '.') for m in modules)
    azure_gate = gate('azure.ai.formrecognizer') or gate('azure.ai.documentintelligence')
    azure_client = False
    clients = {'mindee': False, 'veryfi': False}
    for call in calls:
        f = call.func
        resolved = resolve(f)
        if resolved in ('azure.ai.formrecognizer.DocumentAnalysisClient', 'azure.ai.documentintelligence.DocumentIntelligenceClient'):
            azure_client = True
        if isinstance(f, ast.Attribute) and f.attr in ('DocumentAnalysisClient', 'DocumentIntelligenceClient') and resolved.startswith('azure.'):
            azure_client = True
        for vendor in clients:
            if (isinstance(f, ast.Name) and resolved == vendor + '.Client') or (isinstance(f, ast.Attribute) and f.attr == 'Client' and isinstance(f.value, ast.Name) and f.value.id == vendor and vendor not in shadow):
                clients[vendor] = True
    for call in calls:
        f = call.func
        if isinstance(f, ast.Attribute):
            name = f.attr
            if name in GENERIC_NAMES:
                return True
            args = list(call.args) + [k.value for k in call.keywords]
            if azure_gate and azure_client and name in ('begin_analyze_document', 'begin_analyze_document_from_url'):
                model = list(call.args[:1]) + [k.value for k in call.keywords if k.arg == 'model_id']
                if any(isinstance(a, ast.Constant) and a.value == 'prebuilt-businessCard' for a in model):
                    return True
            if gate('mindee') and clients['mindee'] and name == 'parse' and any((isinstance(a, ast.Name) and a.id == 'BusinessCardV1' and a.id not in shadow) or (isinstance(a, ast.Attribute) and a.attr == 'BusinessCardV1' and a.attr not in shadow) for a in args):
                return True
            if gate('veryfi') and clients['veryfi'] and name in ('process_bussines_card_document', 'process_bussines_card_document_url'):
                return True
        elif isinstance(f, ast.Name) and resolve(f).rsplit('.', 1)[-1] in GENERIC_NAMES:
            if resolve(f).rsplit('.', 1)[-1] not in shadow:
                return True
    return False


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir():
        raise OSError('repository must be a readable directory')
    positive, negative, production, tests = [], [], [], []
    prefixes = [Path(s).as_posix().strip('/') for s in ignore]
    def ignored(rel):
        return any(rel == s or rel.startswith(s + '/') for s in prefixes if s)
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink() and not ignored((Path(directory) / d).relative_to(root).as_posix()))
        for filename in sorted(files):
            path = Path(directory) / filename
            rel = path.relative_to(root)
            if path.is_symlink() or ignored(rel.as_posix()):
                continue
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                yes, no = claims(path.read_text(encoding='utf-8'))
                if yes:
                    positive.append(rel.as_posix())
                if no:
                    negative.append(rel.as_posix())
            if path.suffix == '.py' and not set(rel.parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                if evidence(path.read_text(encoding='utf-8')):
                    target = tests if 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py') else production
                    target.append(rel.as_posix())
    findings = []
    if positive and not production:
        findings.append({'id': 'documented-business-card-extraction-claim-false', 'severity': 'MEDIUM' if tests else 'HIGH', 'message': 'Documented promise lacks production evidence.', 'docs': sorted(positive)})
    if negative and production:
        findings.append({'id': 'documented-no-business-card-extraction-claim-false', 'severity': 'HIGH', 'message': 'Documented denial contradicts production evidence.', 'docs': sorted(negative)})
    return {'verdict': 'FAIL' if findings else 'PASS', 'findings': findings, 'production_evidence': sorted(production), 'test_evidence': sorted(tests)}
