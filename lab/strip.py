import ast,sys
for f in sys.argv[1:]:
    t=ast.parse(open(f,encoding='utf8').read())
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Module,ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0],ast.Expr) and isinstance(getattr(n.body[0],'value',None),ast.Constant) and isinstance(n.body[0].value.value,str):
            n.body=n.body[1:] or [ast.Pass()]
    class R(ast.NodeTransformer):
        def visit_Expr(s,n):
            c=n.value
            if isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute) and isinstance(c.func.value,ast.Name) and c.func.value.id=='logger': return None
            return n
    t=R().visit(t); ast.fix_missing_locations(t)
    for n in ast.walk(t):
        for fld in ('body','orelse','finalbody'):
            if isinstance(getattr(n,fld,None),list) and getattr(n,fld)==[] and fld=='body': setattr(n,fld,[ast.Pass()])
    print(f"##### {f}"); print(ast.unparse(t))
