from tests.modules.ffi.base import BaseFFITest
from topaz.modules.ffi.pointer import W_PointerObject

from rpython.rtyper.lltypesystem import rffi, lltype, llmemory

class TestPointer__NULL(BaseFFITest):
    def test_it_is_null(self, space):
        question = "FFI::Pointer::NULL.null?"
        w_answer = space.execute(question)
        assert self.unwrap(space, w_answer)

    def test_it_is_instance_of_Pointer(self, space):
        question = "FFI::Pointer::NULL.class.equal? FFI::Pointer"
        w_answer = space.execute(question)
        assert self.unwrap(space, w_answer)

    def test_it_eq_nil(self, space):
        question = "FFI::Pointer::NULL == nil"
        w_answer = space.execute(question)
        assert self.unwrap(space, w_answer)

    def test_it_raises_NullPointerError_on_read_write_methods(self, space):
        with self.raises(space, 'FFI::NullPointerError',
                         'read attempt on NULL pointer'):
            space.execute("FFI::Pointer::NULL.read_something")

class TestPointer__new(BaseFFITest):
    def test_it_returns_an_object_eq_to_NULL_when_given_0(self, space):
        question = "FFI::Pointer.new(0) == FFI::Pointer::NULL"
        w_answer = space.execute(question)
        assert self.unwrap(space, w_answer)

    def test_it_serves_as_a_copy_constructor(self, space):
        assert self.ask(space, """
        FFI::Pointer.new(111) == FFI::Pointer.new(FFI::Pointer.new(111))
        """)

    def test_it_saves_a_pointer_to_whatever_address_was_given(self, space):
        char_ptr = lltype.malloc(rffi.CArray(rffi.CHAR), 1, flavor='raw')
        adr = llmemory.cast_ptr_to_adr(char_ptr)
        aint = llmemory.cast_adr_to_int(adr)
        ptr_obj = space.execute("""
        ptr = FFI::Pointer.new(%s)
        """ % aint)
        adr = llmemory.cast_ptr_to_adr(ptr_obj.ptr)
        assert llmemory.cast_adr_to_int(adr) == aint

    def test_it_can_also_be_called_with_a_type_size(self, space):
        char_ptr = lltype.malloc(rffi.CArray(rffi.SHORT), 1, flavor='raw')
        adr = llmemory.cast_ptr_to_adr(char_ptr)
        aint = llmemory.cast_adr_to_int(adr)
        ptr_obj = space.execute("""
        ptr = FFI::Pointer.new(2, %s)
        """ % aint)
        assert space.send(ptr_obj, 'type_size') == 2
        adr = llmemory.cast_ptr_to_adr(ptr_obj.ptr)
        assert llmemory.cast_adr_to_int(adr) == aint

class TestPointer_autorelease(BaseFFITest):
    def test_it(self, space):
        for question in ["FFI::Pointer.new(0).autorelease=(true)",
                         """
                         ptr = FFI::Pointer.new(0)
                         ptr.autorelease=(true)
                         ptr.autorelease?
                         """,
                         "not FFI::Pointer.new(0).autorelease=(false)",
                         """
                         ptr = FFI::Pointer.new(0)
                         ptr.autorelease=(false)
                         not ptr.autorelease?
                         """]:
            assert self.ask(space, question)

class TestPointer_address(BaseFFITest):
    def test_it_returns_the_address(self, space):
        w_res = space.execute("FFI::Pointer.new(42).address")
        assert self.unwrap(space, w_res) == 42

    def test_it_is_aliased_by_to_i(self, space):
        assert self.ask(space, """
        FFI::Pointer::instance_method(:to_i) ==
        FFI::Pointer::instance_method(:address)
        """)

class TestPointer_plus(BaseFFITest):
    def test_it_increases_the_address_by_the_2nd_arg(self, space):
        w_res = space.execute("(FFI::Pointer.new(3) + 2).address")
        assert self.unwrap(space, w_res) == 5

class TestPointer(BaseFFITest):
    def test_its_superclass_is_AbstractMemory(self, space):
        assert self.ask(space,
        "FFI::Pointer.superclass.equal?(FFI::AbstractMemory)")

    def test_it_has_these_methods(self, space):
        # but they don't do anything yet...
        space.execute("FFI::Pointer.new(0).slice(0, 5)")
        with self.raises(space, "TypeError",
                         "can't convert String into Integer"):
            space.execute("FFI::Pointer.new(0).slice('foo', 5)")
            space.execute("FFI::Pointer.new(0).slice(0, 'bar')")
        space.execute("FFI::Pointer.new(0).order(:big)")
        with self.raises(space, "TypeError", "42 is not a symbol"):
            space.execute("FFI::Pointer.new(0).order(42)")
        space.execute("FFI::Pointer.new(0).free")
