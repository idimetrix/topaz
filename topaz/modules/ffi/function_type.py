from topaz.modules.ffi.type import W_TypeObject
from topaz.modules.ffi import type as ffitype
from topaz.modules.ffi._ruby_wrap_llval import (_ruby_wrap_number,
                                                _ruby_wrap_POINTER,
                                                _ruby_wrap_STRING,
                                                _ruby_wrap_llpointer_content,
                                                _ruby_unwrap_llpointer_content)
from topaz.module import ClassDef

from rpython.rtyper.lltypesystem import rffi

def raise_TypeError_if_not_TypeObject(space, w_candidate):
    if not isinstance(w_candidate, W_TypeObject):
        raise space.error(space.w_TypeError,
                          "Invalid parameter type (%s)" %
                          space.str_w(space.send(w_candidate, 'inspect')))

class W_FunctionTypeObject(W_TypeObject):
    classdef = ClassDef('FunctionType', W_TypeObject.classdef)
    _immutable_fields_ = ['arg_types_w', 'w_ret_type']

    @classdef.singleton_method('allocate')
    def singleton_method_allocate(self, space, args_w):
        return W_FunctionTypeObject(space)

    @classdef.method('initialize', arg_types_w='array')
    def method_initialize(self, space, w_ret_type, arg_types_w, w_options=None):
        if w_options is None:
            w_options = space.newhash()
        self.w_options = w_options
        self.space = space

        raise_TypeError_if_not_TypeObject(space, w_ret_type)
        for w_arg_type in arg_types_w:
            raise_TypeError_if_not_TypeObject(space, w_arg_type)

        self.w_ret_type = w_ret_type
        self.arg_types_w = arg_types_w

    def invoke(self, w_proc, args_llp, llp_res):
        space = self.space
        args_w = []
        for i in range(len(self.arg_types_w)):
            w_arg_type = self.arg_types_w[i]
            llp_arg = rffi.cast(rffi.CCHARP, args_llp[i])
            w_arg = self._read_and_wrap_llpointer(space, llp_arg, w_arg_type)
            args_w.append(w_arg)
        w_res = space.send(w_proc, 'call', args_w)
        self._unwrap_and_write_rubyobj(space, w_res, llp_res)

    def _read_and_wrap_llpointer(self, space, llp, w_arg_type):
        assert isinstance(w_arg_type, W_TypeObject)
        typeindex = w_arg_type.typeindex
        for t in ffitype.unrolling_types:
            if t == typeindex:
                return _ruby_wrap_llpointer_content(space, llp, t)
        assert 0

    def _unwrap_and_write_rubyobj(self, space, w_obj, llp_val):
        llp_val = rffi.cast(rffi.CCHARP, llp_val)
        w_ret_type = self.w_ret_type
        assert isinstance(w_ret_type, W_TypeObject)
        typeindex = w_ret_type.typeindex
        for t in ffitype.unrolling_types:
            if t == typeindex:
                _ruby_unwrap_llpointer_content(space, w_obj, llp_val, t)
