//! A test fixture crate for rust2rdf extraction tests.

/// A generic struct with a Clone bound.
pub struct MyStruct<T: Clone> {
    pub field: T,
    pub count: usize,
}

/// An enum with all variant kinds.
pub enum MyEnum {
    /// Unit variant
    Plain,
    /// Tuple variant
    Tuple(i32, String),
    /// Struct variant
    Struct { x: f64, y: f64 },
}

/// A trait with supertraits, required and provided methods.
pub trait MyTrait: Send + Sync {
    /// Required method
    fn required(&self) -> String;
    /// Provided method with default implementation
    fn provided(&self) -> bool {
        true
    }
}

impl<T: Clone + Send + Sync> MyTrait for MyStruct<T> {
    fn required(&self) -> String {
        format!("{}", self.count)
    }
}

/// A fallible function returning Result.
pub fn fallible(x: i32) -> Result<String, std::io::Error> {
    Ok(x.to_string())
}

/// A simple function.
pub fn simple_add(a: i32, b: i32) -> i32 {
    a + b
}

/// A type alias.
pub type StringVec = Vec<String>;

/// A constant.
pub const MY_CONST: i32 = 42;

/// A static variable.
pub static MY_STATIC: &str = "hello";

/// A struct with derive macros.
#[derive(Debug, Clone, PartialEq)]
pub struct Derived {
    pub value: i32,
}

/// An unsafe function.
pub unsafe fn unsafe_fn() {}

/// A nested module.
pub mod nested {
    /// An inner struct.
    pub struct Inner {
        pub data: String,
    }

    /// A deeply nested module.
    pub mod deep {
        /// A deeply nested type.
        pub struct Deep;
    }
}

/// A trait with a lifetime parameter.
pub trait WithLifetime<'a> {
    fn borrow(&'a self) -> &'a str;
}

/// A union type.
pub union MyUnion {
    pub int_val: i32,
    pub float_val: f32,
}
