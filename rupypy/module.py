from pypy.tool.cache import Cache

from rupypy.executioncontext import ExecutionContext


def generate_wrapper(name, orig_func, argspec, self_cls):
    source = []
    source.append("def %s(self, ec, args_w, block):" % orig_func.__name__)
    source.append("    args = ()")
    code = orig_func.__code__
    arg_count = 0
    for i, argname in enumerate(code.co_varnames[:code.co_argcount]):
        if argname in argspec:
            spec = argspec[argname]
            if spec is int:
                source.append("    args += (ec.space.int_w(args_w[%d]),)" % arg_count)
            elif spec is str:
                source.append("    args += (ec.space.str_w(args_w[%d]),)" % arg_count)
            elif spec == "float":
                source.append("    args += (ec.space.float_w(ec.space.send(ec, args_w[%d], ec.space.newsymbol('to_f'))),)" % arg_count)
            elif spec == "symbol":
                source.append("    args += (ec.space.symbol_w(args_w[%d]),)" % arg_count)
            else:
                raise NotImplementedError(spec)
            arg_count += 1
        elif argname.startswith("w_"):
            source.append("    args += (args_w[%d],)" % arg_count)
            arg_count += 1
        elif argname == "self":
            source.append("    assert isinstance(self, self_cls)")
        elif argname == "args_w":
            source.append("    args += (args_w,)")
        elif argname == "block":
            source.append("    args += (block,)")
        elif argname == "space":
            source.append("    args += (ec.space,)")
        elif argname == "ec":
            source.append("    args += (ec,)")
        else:
            raise NotImplementedError(argname)
    source.append("    return func(self, *args)")

    source = "\n".join(source)
    namespace = {"func": orig_func, "self_cls": self_cls}
    exec source in namespace
    return namespace[orig_func.__name__]


class ClassDef(object):
    def __init__(self, name, superclassdef=None):
        self.name = name
        self.methods = {}
        self.app_methods = []
        self.singleton_methods = {}
        self.superclassdef = superclassdef
        self.cls = None

    def _freeze_(self):
        return True

    def include_module(self, mod):
        self.methods.update(mod.moduledef.methods)
        self.app_methods.extend(mod.moduledef.app_methods)

    def method(self, name, **argspec):
        def adder(func):
            self.methods[name] = (func, argspec)
            return func
        return adder

    def app_method(self, source):
        self.app_methods.append(source)

    def singleton_method(self, name, **argspec):
        def adder(func):
            self.singleton_methods[name] = (func, argspec)
            return func
        return adder


class Module(object):
    @classmethod
    def build_object(cls, space):
        from rupypy.objects.functionobject import W_BuiltinFunction
        from rupypy.objects.moduleobject import W_ModuleObject

        w_mod = space.newmodule(cls.moduledef.name)
        for name, (method, argspec) in cls.moduledef.singleton_methods.iteritems():
            func = generate_wrapper(name, method, argspec, W_ModuleObject)
            w_mod.attach_method(space, name, W_BuiltinFunction(name, func))
        return w_mod


class ModuleDef(object):
    def __init__(self, name):
        self.name = name
        self.methods = {}
        self.app_methods = []

        self.singleton_methods = {}
        self.singleton_add_methods = []

    def method(self, name, **argspec):
        def adder(func):
            self.methods[name] = (func, argspec)
        return adder

    def app_method(self, source):
        self.app_methods.append(source)

    def function(self, name, **argspec):
        def adder(func):
            # XXX: should be private, once we have visibility
            self.methods[name] = (func, argspec)
            self.singleton_methods[name] = (func, argspec)
        return adder


class ClassCache(Cache):
    def __init__(self, space):
        super(ClassCache, self).__init__()
        self.space = space

    def _build(self, classdef):
        from rupypy.objects.classobject import W_ClassObject
        from rupypy.objects.functionobject import W_BuiltinFunction

        assert classdef.cls is not None, classdef.name

        if classdef.superclassdef is None:
            superclass = None
        else:
            superclass = self.space.getclassobject(classdef.superclassdef)

        w_class = self.space.newclass(classdef.name, superclass)
        for name, (method, argspec) in classdef.methods.iteritems():
            func = generate_wrapper(name, method, argspec, classdef.cls)
            w_class.define_method(self.space, name, W_BuiltinFunction(name, func))

        for source in classdef.app_methods:
            self.space.execute(ExecutionContext(self.space), source,
                w_self=w_class, w_scope=w_class
            )

        for name, (method, argspec) in classdef.singleton_methods.iteritems():
            func = generate_wrapper(name, method, argspec, W_ClassObject)
            w_class.attach_method(self.space, name, W_BuiltinFunction(name, func))
        return w_class
