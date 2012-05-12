from pypy.rlib import jit
from pypy.rlib.objectmodel import we_are_translated, specialize

from rupypy import consts
from rupypy.error import RubyError
from rupypy.objects.objectobject import W_BaseObject
from rupypy.objects.functionobject import W_FunctionObject


def get_printable_location(pc, bytecode):
    return consts.BYTECODE_NAMES[ord(bytecode.code[pc])]


class Interpreter(object):
    jitdriver = jit.JitDriver(
        greens=["pc", "bytecode"],
        reds=["self", "frame"],
        virtualizables=["frame"],
        get_printable_location=get_printable_location,
    )

    def interpret(self, ec, frame, bytecode):
        pc = 0
        try:
            while True:
                self.jitdriver.jit_merge_point(
                    self=self, bytecode=bytecode, frame=frame, pc=pc
                )
                try:
                    pc = self.handle_bytecode(ec, pc, frame, bytecode)
                except RubyError as e:
                    pc = self.handle_ruby_error(ec, pc, frame, bytecode, e)
        except Return as e:
            return frame.pop()

    def handle_bytecode(self, ec, pc, frame, bytecode):
        instr = ord(bytecode.code[pc])
        pc += 1
        if we_are_translated():
            for i, name in consts.UNROLLING_BYTECODES:
                if i == instr:
                    pc = self.run_instr(ec, name, consts.BYTECODE_NUM_ARGS[i], bytecode, frame, pc)
                    break
            else:
                raise NotImplementedError
        else:
            pc = self.run_instr(ec, consts.BYTECODE_NAMES[instr], consts.BYTECODE_NUM_ARGS[instr], bytecode, frame, pc)
        return pc

    @specialize.arg(2, 3)
    def run_instr(self, ec, name, num_args, bytecode, frame, pc):
        args = ()
        if num_args >= 1:
            args += (ord(bytecode.code[pc]),)
            pc += 1
        if num_args >= 2:
            args += (ord(bytecode.code[pc]),)
            pc += 1
        if num_args >= 3:
            raise NotImplementedError

        method = getattr(self, name)
        res = method(ec, bytecode, frame, pc, *args)
        if res is not None:
            pc = res
        return pc

    def handle_ruby_error(self, space, pc, frame, bytecode, e):
        e.w_value.last_instructions.append(pc)
        block = frame.unrollstack(ApplicationException.kind)
        if block is None:
            raise e
        unroller = ApplicationException(e)
        return block.handle(space, frame, unroller)

    def jump(self, bytecode, frame, cur_pc, target_pc):
        if target_pc < cur_pc:
            self.jitdriver.can_enter_jit(
                self=self, bytecode=bytecode, frame=frame, pc=target_pc,
            )
        return target_pc

    def LOAD_SELF(self, ec, bytecode, frame, pc):
        w_self = frame.w_self
        jit.promote(ec.space.getclass(w_self))
        frame.push(w_self)

    def LOAD_SCOPE(self, space, bytecode, frame, pc):
        frame.push(frame.w_scope)

    def LOAD_CODE(self, space, bytecode, frame, pc):
        frame.push(bytecode)

    def LOAD_CONST(self, space, bytecode, frame, pc, idx):
        frame.push(bytecode.consts_w[idx])

    def LOAD_LOCAL(self, space, bytecode, frame, pc, idx):
        frame.push(frame.locals_w[idx])

    def STORE_LOCAL(self, space, bytecode, frame, pc, idx):
        frame.locals_w[idx] = frame.peek()

    def LOAD_DEREF(self, space, bytecode, frame, pc, idx):
        frame.push(frame.cells[idx].get())

    def STORE_DEREF(self, space, bytecode, frame, pc, idx):
        frame.cells[idx].set(frame.peek())

    def LOAD_CLOSURE(self, space, bytecode, frame, pc, idx):
        frame.push(frame.cells[idx])

    def LOAD_CONSTANT(self, ec, bytecode, frame, pc, idx):
        w_scope = frame.pop()
        w_name = bytecode.consts_w[idx]
        name = ec.space.symbol_w(w_name)
        w_obj = ec.space.find_const(w_scope, name)
        assert w_obj is not None
        frame.push(w_obj)

    def STORE_CONSTANT(self, ec, bytecode, frame, pc, idx):
        w_name = bytecode.consts_w[idx]
        name = ec.space.symbol_w(w_name)
        w_obj = frame.pop()
        ec.space.set_const(frame.w_scope, name, w_obj)
        frame.push(w_obj)

    def LOAD_INSTANCE_VAR(self, ec, bytecode, frame, pc, idx):
        w_name = bytecode.consts_w[idx]
        w_obj = frame.pop()
        w_res = ec.space.find_instance_var(w_obj, ec.space.symbol_w(w_name))
        frame.push(w_res)

    def STORE_INSTANCE_VAR(self, ec, bytecode, frame, pc, idx):
        w_name = bytecode.consts_w[idx]
        w_obj = frame.pop()
        w_value = frame.peek()
        ec.space.set_instance_var(w_obj, ec.space.symbol_w(w_name), w_value)

    @jit.unroll_safe
    def BUILD_ARRAY(self, ec, bytecode, frame, pc, n_items):
        items_w = frame.popitemsreverse(n_items)
        frame.push(ec.space.newarray(items_w))

    def BUILD_RANGE(self, ec, bytecode, frame, pc):
        w_end = frame.pop()
        w_start = frame.pop()
        w_range = ec.space.newrange(w_start, w_end, False)
        frame.push(w_range)

    def BUILD_RANGE_INCLUSIVE(self, ec, bytecode, frame, pc):
        w_end = frame.pop()
        w_start = frame.pop()
        w_range = ec.space.newrange(w_start, w_end, True)
        frame.push(w_range)

    def BUILD_FUNCTION(self, ec, bytecode, frame, pc):
        w_code = frame.pop()
        w_name = frame.pop()
        w_func = ec.space.newfunction(w_name, w_code)
        frame.push(w_func)

    @jit.unroll_safe
    def BUILD_BLOCK(self, space, bytecode, frame, pc, n_cells):
        from rupypy.objects.blockobject import W_BlockObject
        from rupypy.objects.codeobject import W_CodeObject

        cells = [frame.pop() for _ in range(n_cells)]
        w_code = frame.pop()
        assert isinstance(w_code, W_CodeObject)
        block = W_BlockObject(w_code, frame.w_self, frame.w_scope, cells, frame.block)
        frame.push(block)

    def BUILD_CLASS(self, ec, bytecode, frame, pc):
        from rupypy.objects.codeobject import W_CodeObject
        from rupypy.objects.objectobject import W_Object

        w_bytecode = frame.pop()
        superclass = frame.pop()
        w_name = frame.pop()
        w_scope = frame.pop()

        name = ec.space.symbol_w(w_name)
        w_cls = ec.space.find_const(w_scope, name)
        if w_cls is None:
            if superclass is ec.space.w_nil:
                superclass = ec.space.getclassfor(W_Object)
            w_cls = ec.space.newclass(name, superclass)
            ec.space.set_const(w_scope, name, w_cls)

        assert isinstance(w_bytecode, W_CodeObject)
        sub_frame = ec.space.create_frame(w_bytecode, w_cls, w_cls)
        ec.space.execute_frame(ec, sub_frame, w_bytecode)

        frame.push(ec.space.w_nil)

    def BUILD_MODULE(self, ec, bytecode, frame, pc):
        from rupypy.objects.codeobject import W_CodeObject

        w_bytecode = frame.pop()
        w_name = frame.pop()
        w_scope = frame.pop()

        name = ec.space.symbol_w(w_name)
        w_mod = ec.space.find_const(w_scope, name)
        if w_mod is None:
            w_mod = ec.space.newmodule(name)
            ec.space.set_const(w_scope, name, w_mod)

        assert isinstance(w_bytecode, W_CodeObject)
        sub_frame = ec.space.create_frame(w_bytecode, w_mod, w_mod)
        ec.space.execute_frame(ec, sub_frame, w_bytecode)

        frame.push(ec.space.w_nil)

    def COPY_STRING(self, space, bytecode, frame, pc):
        from rupypy.objects.stringobject import W_StringObject

        w_s = frame.pop()
        assert isinstance(w_s, W_StringObject)
        frame.push(w_s.copy())

    def COERCE_ARRAY(self, ec, bytecode, frame, pc):
        from rupypy.objects.arrayobject import W_ArrayObject

        w_obj = frame.pop()
        if w_obj is ec.space.w_nil:
            frame.push(ec.space.newarray([]))
        elif isinstance(w_obj, W_ArrayObject):
            frame.push(w_obj)
        else:
            if ec.space.respond_to(w_obj, ec.space.newsymbol("to_a")):
                w_obj = ec.space.send(ec, w_obj, ec.space.newsymbol("to_a"))
            elif ec.space.respond_to(w_obj, ec.space.newsymbol("to_ary")):
                w_obj = ec.space.send(ec, w_obj, ec.space.newsymbol("to_ary"))
            if not isinstance(w_obj, W_ArrayObject):
                w_obj = ec.space.newarray([w_obj])
            frame.push(w_obj)

    def DEFINE_FUNCTION(self, ec, bytecode, frame, pc):
        w_func = frame.pop()
        w_name = frame.pop()
        w_scope = frame.pop()
        assert isinstance(w_func, W_FunctionObject)
        w_scope.define_method(ec.space, ec.space.symbol_w(w_name), w_func)
        frame.push(ec.space.w_nil)

    def ATTACH_FUNCTION(self, ec, bytecode, frame, pc):
        w_func = frame.pop()
        w_name = frame.pop()
        w_obj = frame.pop()
        assert isinstance(w_func, W_FunctionObject)
        w_obj.attach_method(ec.space, ec.space.symbol_w(w_name), w_func)
        frame.push(ec.space.w_nil)

    @jit.unroll_safe
    def SEND(self, ec, bytecode, frame, pc, meth_idx, num_args):
        args_w = frame.popitemsreverse(num_args)
        w_receiver = frame.pop()
        w_res = ec.space.send(ec, w_receiver, bytecode.consts_w[meth_idx], args_w)
        frame.push(w_res)

    @jit.unroll_safe
    def SEND_BLOCK(self, ec, bytecode, frame, pc, meth_idx, num_args):
        from rupypy.objects.blockobject import W_BlockObject

        w_block = frame.pop()
        args_w = frame.popitemsreverse(num_args - 1)
        w_receiver = frame.pop()
        assert isinstance(w_block, W_BlockObject)
        w_res = ec.space.send(ec, w_receiver, bytecode.consts_w[meth_idx], args_w, block=w_block)
        frame.push(w_res)

    def SEND_SPLAT(self, ec, bytecode, frame, pc, meth_idx):
        args_w = ec.space.listview(frame.pop())
        w_receiver = frame.pop()
        w_res = ec.space.send(ec, w_receiver, bytecode.consts_w[meth_idx], args_w)
        frame.push(w_res)

    def SETUP_EXCEPT(self, space, bytecode, frame, pc, target_pc):
        frame.lastblock = ExceptBlock(target_pc, frame.lastblock, frame.stackpos)

    def SETUP_FINALLY(self, space, bytecode, frame, pc, target_pc):
        frame.lastblock = FinallyBlock(target_pc, frame.lastblock, frame.stackpos)

    def END_FINALLY(self, space, bytecode, frame, pc):
        frame.pop()
        unroller = frame.pop()
        if isinstance(unroller, SuspendedUnroller):
            block = frame.unrollstack(unroller.kind)
            if block is None:
                w_result = unroller.nomoreblocks()
                frame.push(w_result)
                raise Return
            else:
                return block.handle(space, frame, unroller)
        return pc

    def COMPARE_EXC(self, ec, bytecode, frame, pc):
        w_expected = frame.pop()
        w_actual = frame.peek()
        frame.push(ec.space.newbool(w_expected is ec.space.getclass(w_actual)))

    def POP_BLOCK(self, ec, bytecode, frame, pc):
        block = frame.popblock()
        block.cleanup(ec.space, frame)

    def JUMP(self, space, bytecode, frame, pc, target_pc):
        return self.jump(bytecode, frame, pc, target_pc)

    def JUMP_IF_FALSE(self, ec, bytecode, frame, pc, target_pc):
        if ec.space.is_true(frame.pop()):
            return pc
        else:
            return self.jump(bytecode, frame, pc, target_pc)

    def DISCARD_TOP(self, space, bytecode, frame, pc):
        frame.pop()

    def DUP_TOP(self, space, bytecode, frame, pc):
        frame.push(frame.peek())

    def RETURN(self, ec, bytecode, frame, pc):
        w_returnvalue = frame.pop()
        block = frame.unrollstack(ReturnValue.kind)
        if block is None:
            frame.push(w_returnvalue)
            raise Return
        unroller = ReturnValue(w_returnvalue)
        return block.handle(ec.space, frame, unroller)

    @jit.unroll_safe
    def YIELD(self, ec, bytecode, frame, pc, n_args):
        args_w = [None] * n_args
        for i in xrange(n_args - 1, -1, -1):
            args_w[i] = frame.pop()
        w_res = ec.space.invoke_block(ec, frame.block, args_w)
        frame.push(w_res)

    def UNREACHABLE(self, space, bytecode, frame, pc):
        raise Exception


class Return(Exception):
    pass


class SuspendedUnroller(W_BaseObject):
    pass

class ApplicationException(SuspendedUnroller):
    kind = 1 << 1

    def __init__(self, e):
        self.e = e

    def nomoreblocks(self):
        raise self.e

class ReturnValue(SuspendedUnroller):
    kind = 1 << 2

    def __init__(self, w_returnvalue):
        self.w_returnvalue = w_returnvalue

    def nomoreblocks(self):
        return self.w_returnvalue

class FrameBlock(object):
    def __init__(self, target_pc, lastblock, stackdepth):
        self.target_pc = target_pc
        self.lastblock = lastblock
        # Leave one extra item on there, as the return value from this suite.
        self.stackdepth = stackdepth + 1

    @jit.unroll_safe
    def cleanupstack(self, frame):
        while frame.stackpos > self.stackdepth:
            frame.pop()

class ExceptBlock(FrameBlock):
    handling_mask = ApplicationException.kind

    def cleanup(self, space, frame):
        self.cleanupstack(frame)

    def handle(self, space, frame, unroller):
        self.cleanupstack(frame)
        e = unroller.e
        frame.push(unroller)
        frame.push(e.w_value)
        return self.target_pc

class FinallyBlock(FrameBlock):
    # Handles everything.
    handling_mask = -1

    def cleanup(self, space, frame):
        self.cleanupstack(frame)
        frame.push(space.w_nil)

    def handle(self, space, frame, unroller):
        self.cleanupstack(frame)
        frame.push(unroller)
        frame.push(space.w_nil)
        return self.target_pc
