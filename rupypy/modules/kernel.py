import os

from rupypy.module import Module, ModuleDef


class Kernel(Module):
    moduledef = ModuleDef("Kernel")

    @moduledef.method("class")
    def function_class(self, space):
        return space.getclass(self)

    @moduledef.function("puts")
    def function_puts(self, ec, w_obj):
        if w_obj is ec.space.w_nil:
            s = "nil"
        else:
            w_str = ec.space.send(ec, w_obj, ec.space.newsymbol("to_s"))
            s = ec.space.str_w(w_str)
        os.write(1, s)
        os.write(1, "\n")
