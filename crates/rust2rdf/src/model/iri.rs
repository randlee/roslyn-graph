//! IRI minting for Rust symbols in RDF graphs.

use percent_encoding::{utf8_percent_encode, AsciiSet, CONTROLS};

/// Characters that need percent-encoding in IRI path segments.
/// We keep alphanumeric, -, _, ., ~ as unreserved per RFC 3987.
const IRI_ENCODE_SET: &AsciiSet = &CONTROLS
    .add(b' ')
    .add(b'!')
    .add(b'"')
    .add(b'#')
    .add(b'$')
    .add(b'%')
    .add(b'&')
    .add(b'\'')
    .add(b'(')
    .add(b')')
    .add(b'*')
    .add(b'+')
    .add(b',')
    .add(b'/')
    .add(b':')
    .add(b';')
    .add(b'<')
    .add(b'=')
    .add(b'>')
    .add(b'?')
    .add(b'@')
    .add(b'[')
    .add(b']')
    .add(b'^')
    .add(b'`')
    .add(b'{')
    .add(b'|')
    .add(b'}');

/// Generates consistent IRIs for Rust symbols in RDF graphs.
pub struct IriMinter {
    base_uri: String,
}

impl IriMinter {
    pub fn new(base_uri: &str) -> Self {
        Self {
            base_uri: base_uri.trim_end_matches('/').to_string(),
        }
    }

    pub fn base_uri(&self) -> &str {
        &self.base_uri
    }

    /// Escape a string for use in an IRI path segment.
    fn escape(value: &str) -> String {
        utf8_percent_encode(value, IRI_ENCODE_SET).to_string()
    }

    /// IRI for a crate (maps to tg:Assembly / rt:Crate).
    pub fn crate_iri(&self, name: &str, version: &str) -> String {
        format!(
            "{}/crate/{}/{}",
            self.base_uri,
            Self::escape(name),
            Self::escape(version)
        )
    }

    /// IRI for a module (maps to tg:Namespace / rt:Module).
    pub fn module_iri(&self, crate_name: &str, version: &str, module_path: &str) -> String {
        format!(
            "{}/module/{}/{}/{}",
            self.base_uri,
            Self::escape(crate_name),
            Self::escape(version),
            Self::escape(module_path)
        )
    }

    /// IRI for a type (struct, enum, trait, union, type alias).
    pub fn type_iri(&self, crate_name: &str, version: &str, full_path: &str) -> String {
        format!(
            "{}/type/{}/{}/{}",
            self.base_uri,
            Self::escape(crate_name),
            Self::escape(version),
            Self::escape(full_path)
        )
    }

    /// IRI for a member (method, field, constant, associated type).
    pub fn member_iri(&self, type_iri: &str, name: &str, signature: &str) -> String {
        if signature.is_empty() {
            format!("{}/member/{}", type_iri, Self::escape(name))
        } else {
            format!(
                "{}/member/{}({})",
                type_iri,
                Self::escape(name),
                Self::escape(signature)
            )
        }
    }

    /// IRI for a function parameter.
    pub fn parameter_iri(&self, method_iri: &str, ordinal: usize) -> String {
        format!("{method_iri}/param/{ordinal}")
    }

    /// IRI for a type parameter.
    pub fn type_parameter_iri(&self, owner_iri: &str, ordinal: usize) -> String {
        format!("{owner_iri}/typeparam/{ordinal}")
    }

    /// IRI for an enum variant.
    pub fn variant_iri(&self, enum_iri: &str, name: &str) -> String {
        format!("{}/variant/{}", enum_iri, Self::escape(name))
    }

    /// IRI for an impl block (uses rustdoc item ID for uniqueness).
    pub fn impl_iri(&self, crate_name: &str, version: &str, impl_id: &str) -> String {
        format!(
            "{}/impl/{}/{}/{}",
            self.base_uri,
            Self::escape(crate_name),
            Self::escape(version),
            Self::escape(impl_id)
        )
    }

    /// IRI for a lifetime parameter.
    pub fn lifetime_iri(&self, owner_iri: &str, name: &str) -> String {
        // Strip leading ' from lifetime name
        let clean_name = name.strip_prefix('\'').unwrap_or(name);
        format!("{}/lifetime/{}", owner_iri, Self::escape(clean_name))
    }

    /// IRI for a primitive type.
    pub fn primitive_type_iri(&self, name: &str) -> String {
        format!("{}/type/_primitive_/{}", self.base_uri, Self::escape(name))
    }

    /// IRI for a tuple type.
    pub fn tuple_type_iri(&self, element_count: usize) -> String {
        format!("{}/type/_tuple_/{}", self.base_uri, element_count)
    }

    /// IRI for a slice type.
    pub fn slice_type_iri(&self, element_type_name: &str) -> String {
        format!(
            "{}/type/_slice_/{}",
            self.base_uri,
            Self::escape(element_type_name)
        )
    }

    /// IRI for an array type.
    pub fn array_type_iri(&self, element_type_name: &str, length: &str) -> String {
        format!(
            "{}/type/_array_/{}/{}",
            self.base_uri,
            Self::escape(element_type_name),
            Self::escape(length)
        )
    }

    /// IRI for a reference type.
    pub fn ref_type_iri(&self, target_type_name: &str, mutable: bool) -> String {
        let mutability = if mutable { "mut" } else { "ref" };
        format!(
            "{}/type/_{}_/{}",
            self.base_uri,
            mutability,
            Self::escape(target_type_name)
        )
    }

    /// IRI for a raw pointer type.
    pub fn raw_pointer_type_iri(&self, target_type_name: &str, mutable: bool) -> String {
        let mutability = if mutable { "mut" } else { "const" };
        format!(
            "{}/type/_ptr_{}_/{}",
            self.base_uri,
            mutability,
            Self::escape(target_type_name)
        )
    }
}
