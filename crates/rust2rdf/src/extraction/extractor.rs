//! Crate extraction engine: walks rustdoc JSON and emits RDF triples.
//!
//! The [`CrateExtractor`] traverses every item in a [`Crate`] index, resolving
//! types and relationships, and emitting triples through a [`TriplesEmitter`].

use std::collections::HashSet;

use crate::emitter::TriplesEmitter;
use crate::model::iri::IriMinter;
use crate::model::ontology::{rt, standard, tg};

use super::rustdoc_model::{
    Crate, FunctionHeader, FunctionSignature, GenericBound, GenericParamDefKind, Generics, Item,
    ItemEnum, ResolvedPath, StructKind, Type, VariantData, VariantKind, Visibility,
};

// ---------------------------------------------------------------------------
// ExtractionOptions
// ---------------------------------------------------------------------------

/// Options controlling what gets extracted.
pub struct ExtractionOptions {
    pub base_uri: String,
    pub include_impls: bool,
    pub include_attributes: bool,
    pub extract_error_types: bool,
    pub extract_derives: bool,
}

impl Default for ExtractionOptions {
    fn default() -> Self {
        Self {
            base_uri: "http://rust.example".to_string(),
            include_impls: true,
            include_attributes: true,
            extract_error_types: true,
            extract_derives: true,
        }
    }
}

// ---------------------------------------------------------------------------
// CrateExtractor
// ---------------------------------------------------------------------------

/// Walks a rustdoc [`Crate`] and emits RDF triples via a [`TriplesEmitter`].
pub struct CrateExtractor<'a, E: TriplesEmitter> {
    emitter: &'a mut E,
    iris: IriMinter,
    crate_data: &'a Crate,
    crate_name: String,
    crate_version: String,
    options: ExtractionOptions,
    emitted_types: HashSet<String>,
    emitted_modules: HashSet<String>,
}

impl<'a, E: TriplesEmitter> CrateExtractor<'a, E> {
    /// Create a new extractor. Call [`extract`](Self::extract) to run.
    pub fn new(emitter: &'a mut E, crate_data: &'a Crate, options: ExtractionOptions) -> Self {
        // Determine crate name from root module item.
        let crate_name = crate_data
            .index
            .get(&crate_data.root.0)
            .and_then(|item| item.name.clone())
            .unwrap_or_else(|| "unknown".to_string());

        let crate_version = crate_data
            .crate_version
            .clone()
            .unwrap_or_else(|| "0.0.0".to_string());

        let iris = IriMinter::new(&options.base_uri);

        Self {
            emitter,
            iris,
            crate_data,
            crate_name,
            crate_version,
            options,
            emitted_types: HashSet::new(),
            emitted_modules: HashSet::new(),
        }
    }

    // -----------------------------------------------------------------------
    // Public entry point
    // -----------------------------------------------------------------------

    /// Run the full extraction, emitting all triples.
    pub fn extract(&mut self) {
        self.register_prefixes();
        self.emit_crate_node();
        self.emit_external_crates();
        self.walk_module(&self.crate_data.root.0.clone(), &self.crate_name.clone());
        if self.options.include_impls {
            self.process_all_impls();
        }
    }

    // -----------------------------------------------------------------------
    // Prefix registration
    // -----------------------------------------------------------------------

    fn register_prefixes(&mut self) {
        self.emitter.add_prefix("rdf", standard::RDF);
        self.emitter.add_prefix("rdfs", standard::RDFS);
        self.emitter.add_prefix("xsd", standard::XSD);
        self.emitter.add_prefix(tg::PREFIX, tg::NS);
        self.emitter.add_prefix(rt::PREFIX, rt::NS);
    }

    // -----------------------------------------------------------------------
    // Crate node
    // -----------------------------------------------------------------------

    fn emit_crate_node(&mut self) {
        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        self.emitter
            .emit_iri(&crate_iri, standard::RDF_TYPE, rt::CRATE);
        self.emitter
            .emit_iri(&crate_iri, standard::RDF_TYPE, tg::ASSEMBLY);
        self.emitter
            .emit_literal(&crate_iri, tg::NAME, &self.crate_name);
        self.emitter
            .emit_literal(&crate_iri, tg::LANGUAGE, "rust");
        self.emitter
            .emit_literal(&crate_iri, tg::VERSION, &self.crate_version);
    }

    // -----------------------------------------------------------------------
    // External crate dependencies
    // -----------------------------------------------------------------------

    fn emit_external_crates(&mut self) {
        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        for ext in self.crate_data.external_crates.values() {
            let dep_iri = self.iris.crate_iri(&ext.name, "0.0.0");
            self.emitter.emit_iri(&crate_iri, rt::DEPENDS_ON, &dep_iri);
            self.emitter
                .emit_iri(&dep_iri, standard::RDF_TYPE, rt::CRATE);
            self.emitter.emit_literal(&dep_iri, tg::NAME, &ext.name);
        }
    }

    // -----------------------------------------------------------------------
    // Module walking
    // -----------------------------------------------------------------------

    fn walk_module(&mut self, item_id: &str, module_path: &str) {
        let item = match self.crate_data.index.get(item_id) {
            Some(i) => i,
            None => return,
        };

        if let ItemEnum::Module { ref items, .. } = item.inner {
            // Emit module node (but not the root module as namespace since it
            // doubles as the crate itself).
            let is_root = item_id == self.crate_data.root.0;
            if !is_root {
                self.emit_module_node(module_path, item);
            }

            let child_ids: Vec<String> = items.iter().map(|id| id.0.clone()).collect();
            for child_id in &child_ids {
                self.walk_item(child_id, module_path);
            }
        }
    }

    fn emit_module_node(&mut self, module_path: &str, item: &Item) {
        if self.emitted_modules.contains(module_path) {
            return;
        }
        self.emitted_modules.insert(module_path.to_string());

        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);
        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);

        self.emitter
            .emit_iri(&module_iri, standard::RDF_TYPE, rt::MODULE);
        self.emitter
            .emit_iri(&module_iri, standard::RDF_TYPE, tg::NAMESPACE);

        let name = item.name.as_deref().unwrap_or(module_path);
        self.emitter.emit_literal(&module_iri, tg::NAME, name);
        self.emitter
            .emit_literal(&module_iri, tg::FULL_NAME, module_path);
        self.emitter
            .emit_iri(&module_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);

        // Emit accessibility
        let vis = visibility_str(&item.visibility);
        self.emitter
            .emit_literal(&module_iri, tg::ACCESSIBILITY, vis);

        // Parent namespace
        if let Some(parent_path) = module_path.rsplit_once("::").map(|(p, _)| p) {
            let parent_iri =
                self.iris
                    .module_iri(&self.crate_name, &self.crate_version, parent_path);
            self.emitter
                .emit_iri(&module_iri, tg::PARENT_NAMESPACE, &parent_iri);
        }
    }

    // -----------------------------------------------------------------------
    // Item dispatch
    // -----------------------------------------------------------------------

    fn walk_item(&mut self, item_id: &str, parent_module_path: &str) {
        let item = match self.crate_data.index.get(item_id) {
            Some(i) => i,
            None => return,
        };

        match &item.inner {
            ItemEnum::Module { .. } => {
                let name = item.name.as_deref().unwrap_or("unnamed");
                let child_path = format!("{parent_module_path}::{name}");
                self.walk_module(item_id, &child_path);
            }
            ItemEnum::Struct { .. } => {
                self.extract_struct(item_id, item, parent_module_path);
            }
            ItemEnum::Enum { .. } => {
                self.extract_enum(item_id, item, parent_module_path);
            }
            ItemEnum::Trait { .. } => {
                self.extract_trait(item_id, item, parent_module_path);
            }
            ItemEnum::Function { .. } => {
                self.extract_module_function(item_id, item, parent_module_path);
            }
            ItemEnum::Constant { .. } => {
                self.extract_constant(item, parent_module_path);
            }
            ItemEnum::Static { .. } => {
                self.extract_static(item, parent_module_path);
            }
            ItemEnum::TypeAlias { .. } => {
                self.extract_type_alias(item, parent_module_path);
            }
            ItemEnum::Union { .. } => {
                self.extract_union(item_id, item, parent_module_path);
            }
            ItemEnum::Use { .. } | ItemEnum::Impl { .. } => {
                // Impls processed in a separate pass; Use items are skipped.
            }
            _ => {}
        }
    }

    // -----------------------------------------------------------------------
    // Struct extraction
    // -----------------------------------------------------------------------

    fn extract_struct(&mut self, item_id: &str, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };
        let full_path = format!("{module_path}::{name}");
        let type_iri = self
            .iris
            .type_iri(&self.crate_name, &self.crate_version, &full_path);

        if !self.emitted_types.insert(type_iri.clone()) {
            return;
        }

        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        let module_iri = self
            .iris
            .module_iri(&self.crate_name, &self.crate_version, module_path);

        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, tg::STRUCT);
        self.emitter.emit_literal(&type_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&type_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&type_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);
        self.emitter
            .emit_iri(&type_iri, tg::IN_NAMESPACE, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&type_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Struct {
            ref kind,
            ref generics,
            ..
        } = item.inner
        {
            // Mark generic if has type params
            let has_type_params = generics
                .params
                .iter()
                .any(|p| matches!(p.kind, GenericParamDefKind::Type { .. }));
            if has_type_params {
                self.emitter.emit_bool(&type_iri, tg::IS_GENERIC, true);
            }

            self.extract_generics(generics, &type_iri);

            // Extract fields
            match kind {
                StructKind::Plain { ref fields, .. } => {
                    for field_id in fields {
                        self.extract_field(&field_id.0, &type_iri);
                    }
                }
                StructKind::Tuple(ref field_ids) => {
                    for field_id in field_ids.iter().flatten() {
                        self.extract_field(&field_id.0, &type_iri);
                    }
                }
                StructKind::Unit => {}
            }
        }

        // Extract derives from impls associated with this struct
        if self.options.extract_derives {
            self.extract_derives_for_item(item_id, &type_iri);
        }
    }

    // -----------------------------------------------------------------------
    // Enum extraction
    // -----------------------------------------------------------------------

    fn extract_enum(&mut self, item_id: &str, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };
        let full_path = format!("{module_path}::{name}");
        let type_iri = self
            .iris
            .type_iri(&self.crate_name, &self.crate_version, &full_path);

        if !self.emitted_types.insert(type_iri.clone()) {
            return;
        }

        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        let module_iri = self
            .iris
            .module_iri(&self.crate_name, &self.crate_version, module_path);

        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, tg::ENUM);
        self.emitter.emit_literal(&type_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&type_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&type_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);
        self.emitter
            .emit_iri(&type_iri, tg::IN_NAMESPACE, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&type_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Enum {
            ref generics,
            ref variants,
            ..
        } = item.inner
        {
            let has_type_params = generics
                .params
                .iter()
                .any(|p| matches!(p.kind, GenericParamDefKind::Type { .. }));
            if has_type_params {
                self.emitter.emit_bool(&type_iri, tg::IS_GENERIC, true);
            }

            self.extract_generics(generics, &type_iri);

            // Extract variants
            for variant_id in variants {
                self.extract_variant(&variant_id.0, &type_iri);
            }
        }

        if self.options.extract_derives {
            self.extract_derives_for_item(item_id, &type_iri);
        }
    }

    fn extract_variant(&mut self, variant_id: &str, enum_iri: &str) {
        let item = match self.crate_data.index.get(variant_id) {
            Some(i) => i,
            None => return,
        };

        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let variant_iri = self.iris.variant_iri(enum_iri, &name);

        self.emitter
            .emit_iri(&variant_iri, standard::RDF_TYPE, rt::ENUM_VARIANT);
        self.emitter.emit_literal(&variant_iri, tg::NAME, &name);
        self.emitter
            .emit_iri(enum_iri, rt::HAS_VARIANT, &variant_iri);

        if let ItemEnum::Variant(VariantData { ref kind, .. }) = item.inner {
            match kind {
                VariantKind::Plain => {
                    self.emitter
                        .emit_literal(&variant_iri, rt::VARIANT_KIND, "plain");
                }
                VariantKind::Tuple(ref field_ids) => {
                    self.emitter
                        .emit_literal(&variant_iri, rt::VARIANT_KIND, "tuple");
                    for field_id in field_ids.iter().flatten() {
                        self.extract_variant_field(&field_id.0, &variant_iri);
                    }
                }
                VariantKind::Struct { ref fields, .. } => {
                    self.emitter
                        .emit_literal(&variant_iri, rt::VARIANT_KIND, "struct");
                    for field_id in fields {
                        self.extract_variant_field(&field_id.0, &variant_iri);
                    }
                }
            }
        }
    }

    fn extract_variant_field(&mut self, field_id: &str, variant_iri: &str) {
        let item = match self.crate_data.index.get(field_id) {
            Some(i) => i,
            None => return,
        };

        let name = item.name.as_deref().unwrap_or("unnamed");

        if let ItemEnum::StructField(ref ty) = item.inner {
            let field_iri = self.iris.member_iri(variant_iri, name, "");
            self.emitter
                .emit_iri(&field_iri, standard::RDF_TYPE, tg::FIELD);
            self.emitter.emit_literal(&field_iri, tg::NAME, name);
            self.emitter
                .emit_iri(variant_iri, rt::VARIANT_FIELD, &field_iri);

            if let Some(type_iri) = self.resolve_type_to_iri(ty) {
                self.emitter
                    .emit_iri(&field_iri, tg::FIELD_TYPE, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Trait extraction
    // -----------------------------------------------------------------------

    fn extract_trait(&mut self, _item_id: &str, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };
        let full_path = format!("{module_path}::{name}");
        let type_iri = self
            .iris
            .type_iri(&self.crate_name, &self.crate_version, &full_path);

        if !self.emitted_types.insert(type_iri.clone()) {
            return;
        }

        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        let module_iri = self
            .iris
            .module_iri(&self.crate_name, &self.crate_version, module_path);

        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, tg::INTERFACE);
        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, rt::TRAIT);
        self.emitter.emit_literal(&type_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&type_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&type_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);
        self.emitter
            .emit_iri(&type_iri, tg::IN_NAMESPACE, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&type_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Trait {
            ref generics,
            ref bounds,
            ref items,
            is_unsafe,
            ..
        } = item.inner
        {
            if is_unsafe {
                self.emitter.emit_bool(&type_iri, rt::IS_UNSAFE, true);
            }

            let has_type_params = generics
                .params
                .iter()
                .any(|p| matches!(p.kind, GenericParamDefKind::Type { .. }));
            if has_type_params {
                self.emitter.emit_bool(&type_iri, tg::IS_GENERIC, true);
            }

            self.extract_generics(generics, &type_iri);

            // Supertraits
            for bound in bounds {
                if let GenericBound::TraitBound { ref trait_, .. } = bound {
                    let supertrait_name = &trait_.path;
                    let supertrait_iri = self.resolve_path_to_iri(trait_);
                    self.emitter
                        .emit_iri(&type_iri, rt::SUPER_TRAIT, &supertrait_iri);
                    // Ensure the supertrait node exists minimally
                    self.ensure_external_type_emitted(&supertrait_iri, supertrait_name);
                }
            }

            // Trait methods
            let method_ids: Vec<String> = items.iter().map(|id| id.0.clone()).collect();
            for method_id in &method_ids {
                self.extract_type_method(method_id, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Function extraction (module-level)
    // -----------------------------------------------------------------------

    fn extract_module_function(&mut self, _item_id: &str, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let full_path = format!("{module_path}::{name}");
        // Module-level functions: use module_iri as the "owner".
        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);
        let fn_iri = self.iris.member_iri(&module_iri, &name, "");

        self.emitter
            .emit_iri(&fn_iri, standard::RDF_TYPE, tg::METHOD);
        self.emitter.emit_literal(&fn_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&fn_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&module_iri, tg::HAS_MEMBER, &fn_iri);
        self.emitter
            .emit_iri(&fn_iri, tg::MEMBER_OF, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&fn_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Function {
            ref sig,
            ref generics,
            ref header,
            ..
        } = item.inner
        {
            self.extract_function_details(&fn_iri, sig, generics, header);

            // Error type extraction for Result return types
            if self.options.extract_error_types {
                self.extract_error_type(&fn_iri, sig);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Type method extraction (trait methods, impl methods)
    // -----------------------------------------------------------------------

    fn extract_type_method(&mut self, method_id: &str, owner_iri: &str) {
        let item = match self.crate_data.index.get(method_id) {
            Some(i) => i,
            None => return,
        };

        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let method_iri = self.iris.member_iri(owner_iri, &name, "");

        self.emitter
            .emit_iri(&method_iri, standard::RDF_TYPE, tg::METHOD);
        self.emitter.emit_literal(&method_iri, tg::NAME, &name);
        self.emitter
            .emit_iri(owner_iri, tg::HAS_MEMBER, &method_iri);
        self.emitter
            .emit_iri(&method_iri, tg::MEMBER_OF, owner_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter
            .emit_literal(&method_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Function {
            ref sig,
            ref generics,
            ref header,
            has_body,
        } = item.inner
        {
            self.extract_function_details(&method_iri, sig, generics, header);

            // For trait methods: has_body means "provided" (default impl)
            if !has_body {
                self.emitter
                    .emit_bool(&method_iri, tg::IS_ABSTRACT, true);
            }

            if self.options.extract_error_types {
                self.extract_error_type(&method_iri, sig);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Constant extraction
    // -----------------------------------------------------------------------

    fn extract_constant(&mut self, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);
        let const_iri = self.iris.member_iri(&module_iri, &name, "");

        self.emitter
            .emit_iri(&const_iri, standard::RDF_TYPE, tg::FIELD);
        self.emitter
            .emit_iri(&const_iri, standard::RDF_TYPE, rt::CONSTANT);
        self.emitter.emit_literal(&const_iri, tg::NAME, &name);
        self.emitter.emit_bool(&const_iri, tg::IS_CONST, true);
        self.emitter
            .emit_iri(&module_iri, tg::HAS_MEMBER, &const_iri);
        self.emitter
            .emit_iri(&const_iri, tg::MEMBER_OF, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter
            .emit_literal(&const_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Constant { ref type_, .. } = item.inner {
            if let Some(type_iri) = self.resolve_type_to_iri(type_) {
                self.emitter
                    .emit_iri(&const_iri, tg::FIELD_TYPE, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Static extraction
    // -----------------------------------------------------------------------

    fn extract_static(&mut self, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);
        let static_iri = self.iris.member_iri(&module_iri, &name, "");

        self.emitter
            .emit_iri(&static_iri, standard::RDF_TYPE, rt::STATIC);
        self.emitter.emit_literal(&static_iri, tg::NAME, &name);
        self.emitter
            .emit_iri(&module_iri, tg::HAS_MEMBER, &static_iri);
        self.emitter
            .emit_iri(&static_iri, tg::MEMBER_OF, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter
            .emit_literal(&static_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Static {
            ref type_,
            is_mutable,
            ..
        } = item.inner
        {
            if is_mutable {
                self.emitter.emit_bool(&static_iri, rt::IS_MUTABLE, true);
            }
            if let Some(type_iri) = self.resolve_type_to_iri(type_) {
                self.emitter
                    .emit_iri(&static_iri, tg::FIELD_TYPE, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // TypeAlias extraction
    // -----------------------------------------------------------------------

    fn extract_type_alias(&mut self, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };

        let full_path = format!("{module_path}::{name}");
        let type_iri = self
            .iris
            .type_iri(&self.crate_name, &self.crate_version, &full_path);

        if !self.emitted_types.insert(type_iri.clone()) {
            return;
        }

        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);

        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, rt::TYPE_ALIAS);
        self.emitter.emit_literal(&type_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&type_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&type_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);
        self.emitter
            .emit_iri(&type_iri, tg::IN_NAMESPACE, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&type_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::TypeAlias {
            type_: Some(ref target_type),
            ..
        } = item.inner
        {
            if let Some(target_iri) = self.resolve_type_to_iri(target_type) {
                self.emitter
                    .emit_iri(&type_iri, tg::RELATED_TO, &target_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Union extraction
    // -----------------------------------------------------------------------

    fn extract_union(&mut self, _item_id: &str, item: &Item, module_path: &str) {
        let name = match &item.name {
            Some(n) => n.clone(),
            None => return,
        };
        let full_path = format!("{module_path}::{name}");
        let type_iri = self
            .iris
            .type_iri(&self.crate_name, &self.crate_version, &full_path);

        if !self.emitted_types.insert(type_iri.clone()) {
            return;
        }

        let crate_iri = self.iris.crate_iri(&self.crate_name, &self.crate_version);
        let module_iri =
            self.iris
                .module_iri(&self.crate_name, &self.crate_version, module_path);

        self.emitter
            .emit_iri(&type_iri, standard::RDF_TYPE, rt::UNION);
        self.emitter.emit_literal(&type_iri, tg::NAME, &name);
        self.emitter
            .emit_literal(&type_iri, tg::FULL_NAME, &full_path);
        self.emitter
            .emit_iri(&type_iri, tg::DEFINED_IN_ASSEMBLY, &crate_iri);
        self.emitter
            .emit_iri(&type_iri, tg::IN_NAMESPACE, &module_iri);

        let vis = visibility_str(&item.visibility);
        self.emitter.emit_literal(&type_iri, tg::ACCESSIBILITY, vis);

        if let ItemEnum::Union {
            ref generics,
            ref fields,
            ..
        } = item.inner
        {
            self.extract_generics(generics, &type_iri);

            for field_id in fields {
                self.extract_field(&field_id.0, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Field extraction
    // -----------------------------------------------------------------------

    fn extract_field(&mut self, field_id: &str, owner_iri: &str) {
        let item = match self.crate_data.index.get(field_id) {
            Some(i) => i,
            None => return,
        };

        let name = item.name.as_deref().unwrap_or("unnamed");

        if let ItemEnum::StructField(ref ty) = item.inner {
            let field_iri = self.iris.member_iri(owner_iri, name, "");

            self.emitter
                .emit_iri(&field_iri, standard::RDF_TYPE, tg::FIELD);
            self.emitter.emit_literal(&field_iri, tg::NAME, name);
            self.emitter
                .emit_iri(owner_iri, tg::HAS_MEMBER, &field_iri);
            self.emitter
                .emit_iri(&field_iri, tg::MEMBER_OF, owner_iri);

            let vis = visibility_str(&item.visibility);
            self.emitter
                .emit_literal(&field_iri, tg::ACCESSIBILITY, vis);

            if let Some(type_iri) = self.resolve_type_to_iri(ty) {
                self.emitter
                    .emit_iri(&field_iri, tg::FIELD_TYPE, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Impl block processing
    // -----------------------------------------------------------------------

    fn process_all_impls(&mut self) {
        // Collect all impl item IDs first to avoid borrow issues
        let impl_ids: Vec<String> = self
            .crate_data
            .index
            .iter()
            .filter(|(_, item)| matches!(item.inner, ItemEnum::Impl { .. }))
            .map(|(id, _)| id.clone())
            .collect();

        for impl_id in &impl_ids {
            self.process_impl(impl_id);
        }
    }

    fn process_impl(&mut self, impl_id: &str) {
        let item = match self.crate_data.index.get(impl_id) {
            Some(i) => i,
            None => return,
        };

        if let ItemEnum::Impl {
            ref trait_,
            ref for_,
            ref items,
            is_synthetic,
            ref blanket_impl,
            ..
        } = item.inner
        {
            // Skip synthetic impls (auto traits like Send/Sync) and blanket impls
            if is_synthetic || blanket_impl.is_some() {
                return;
            }

            // Resolve the "for" type to an IRI
            let for_iri = match self.resolve_type_to_iri(for_) {
                Some(iri) => iri,
                None => return,
            };

            // Only process impls for types defined in this crate
            if !self.emitted_types.contains(&for_iri) {
                return;
            }

            let impl_iri =
                self.iris
                    .impl_iri(&self.crate_name, &self.crate_version, impl_id);

            if let Some(ref trait_path) = trait_ {
                // Trait impl
                let trait_iri = self.resolve_path_to_iri(trait_path);

                self.emitter
                    .emit_iri(&impl_iri, standard::RDF_TYPE, rt::TRAIT_IMPL);
                self.emitter.emit_iri(&impl_iri, rt::IMPL_FOR, &for_iri);
                self.emitter
                    .emit_iri(&impl_iri, rt::IMPL_TRAIT, &trait_iri);
                self.emitter
                    .emit_iri(&for_iri, tg::IMPLEMENTS, &trait_iri);

                // Ensure trait node exists
                self.ensure_external_type_emitted(&trait_iri, &trait_path.path);
            } else {
                // Inherent impl — add methods directly as members of the type
                self.emitter
                    .emit_iri(&impl_iri, standard::RDF_TYPE, rt::INHERENT_IMPL);
                self.emitter.emit_iri(&impl_iri, rt::IMPL_FOR, &for_iri);
            }

            // Process impl items (methods, associated types, etc.)
            let method_ids: Vec<String> = items.iter().map(|id| id.0.clone()).collect();
            for method_id in &method_ids {
                // For inherent impls, methods belong to the type directly.
                // For trait impls, methods belong to the impl node.
                let owner_iri = if trait_.is_none() {
                    for_iri.clone()
                } else {
                    impl_iri.clone()
                };
                self.extract_impl_item(method_id, &owner_iri);
            }
        }
    }

    fn extract_impl_item(&mut self, item_id: &str, owner_iri: &str) {
        let item = match self.crate_data.index.get(item_id) {
            Some(i) => i,
            None => return,
        };

        match &item.inner {
            ItemEnum::Function { .. } => {
                self.extract_type_method(item_id, owner_iri);
            }
            ItemEnum::AssocType { .. } | ItemEnum::AssocConst { .. } => {
                // Associated types and consts — emit minimal info
                if let Some(ref name) = item.name {
                    let member_iri = self.iris.member_iri(owner_iri, name, "");
                    self.emitter
                        .emit_iri(&member_iri, standard::RDF_TYPE, tg::MEMBER);
                    self.emitter.emit_literal(&member_iri, tg::NAME, name);
                    self.emitter
                        .emit_iri(owner_iri, tg::HAS_MEMBER, &member_iri);
                }
            }
            _ => {}
        }
    }

    // -----------------------------------------------------------------------
    // Derive macro extraction
    // -----------------------------------------------------------------------

    fn extract_derives_for_item(&mut self, item_id: &str, type_iri: &str) {
        // Find impl blocks associated with this type that have `automatically_derived`
        // in their attrs — these are derive macro impls.
        let item = match self.crate_data.index.get(item_id) {
            Some(i) => i,
            None => return,
        };

        // Get the impl IDs from the item
        let impl_ids = match &item.inner {
            ItemEnum::Struct { ref impls, .. } => {
                impls.iter().map(|id| id.0.clone()).collect::<Vec<_>>()
            }
            ItemEnum::Enum { ref impls, .. } => {
                impls.iter().map(|id| id.0.clone()).collect::<Vec<_>>()
            }
            _ => return,
        };

        for imp_id in &impl_ids {
            let imp_item = match self.crate_data.index.get(imp_id) {
                Some(i) => i,
                None => continue,
            };

            // Check if it's an automatically_derived impl
            let is_auto_derived = imp_item.attrs.iter().any(|attr| match attr {
                serde_json::Value::String(s) => s == "automatically_derived",
                _ => false,
            });

            if !is_auto_derived {
                continue;
            }

            // Extract the trait name from the impl
            if let ItemEnum::Impl {
                trait_: Some(ref trait_path),
                ..
            } = imp_item.inner
            {
                self.emitter
                    .emit_literal(type_iri, rt::DERIVES, &trait_path.path);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Generics extraction (Phase 8)
    // -----------------------------------------------------------------------

    fn extract_generics(&mut self, generics: &Generics, owner_iri: &str) {
        for (ordinal, param) in generics.params.iter().enumerate() {
            match &param.kind {
                GenericParamDefKind::Type { ref bounds, .. } => {
                    let tp_iri = self.iris.type_parameter_iri(owner_iri, ordinal);
                    self.emitter
                        .emit_iri(&tp_iri, standard::RDF_TYPE, tg::TYPE_PARAMETER);
                    self.emitter.emit_literal(&tp_iri, tg::NAME, &param.name);
                    self.emitter.emit_int(&tp_iri, tg::ORDINAL, ordinal as i64);
                    self.emitter
                        .emit_iri(owner_iri, tg::HAS_TYPE_PARAMETER, &tp_iri);
                    self.emitter
                        .emit_iri(&tp_iri, tg::TYPE_PARAMETER_OF, owner_iri);

                    // Trait bounds
                    for bound in bounds {
                        if let GenericBound::TraitBound { ref trait_, .. } = bound {
                            let bound_iri = self.resolve_path_to_iri(trait_);
                            self.emitter
                                .emit_iri(&tp_iri, rt::TRAIT_BOUND, &bound_iri);
                            self.ensure_external_type_emitted(&bound_iri, &trait_.path);
                        }
                    }
                }
                GenericParamDefKind::Lifetime { .. } => {
                    let lt_iri = self.iris.lifetime_iri(owner_iri, &param.name);
                    self.emitter
                        .emit_iri(&lt_iri, standard::RDF_TYPE, rt::LIFETIME);
                    self.emitter.emit_literal(&lt_iri, tg::NAME, &param.name);
                    self.emitter
                        .emit_iri(owner_iri, rt::HAS_LIFETIME, &lt_iri);
                }
                GenericParamDefKind::Const { ref type_, .. } => {
                    let cp_iri = self.iris.type_parameter_iri(owner_iri, ordinal);
                    self.emitter
                        .emit_iri(&cp_iri, standard::RDF_TYPE, rt::CONST_PARAM);
                    self.emitter.emit_literal(&cp_iri, tg::NAME, &param.name);
                    self.emitter.emit_int(&cp_iri, tg::ORDINAL, ordinal as i64);
                    self.emitter
                        .emit_iri(owner_iri, tg::HAS_TYPE_PARAMETER, &cp_iri);

                    if let Some(type_iri) = self.resolve_type_to_iri(type_) {
                        self.emitter
                            .emit_iri(&cp_iri, tg::PARAMETER_TYPE, &type_iri);
                    }
                }
                GenericParamDefKind::Unknown => {}
            }
        }
    }

    // -----------------------------------------------------------------------
    // Function signature extraction (Phase 8)
    // -----------------------------------------------------------------------

    fn extract_function_details(
        &mut self,
        fn_iri: &str,
        sig: &FunctionSignature,
        generics: &Generics,
        header: &FunctionHeader,
    ) {
        // Header flags
        if header.is_unsafe {
            self.emitter.emit_bool(fn_iri, rt::IS_UNSAFE, true);
        }
        if header.is_async {
            self.emitter.emit_bool(fn_iri, tg::IS_ASYNC, true);
        }
        if header.is_const {
            self.emitter.emit_bool(fn_iri, tg::IS_CONST, true);
        }

        // Generics on the function itself
        let has_type_params = generics
            .params
            .iter()
            .any(|p| matches!(p.kind, GenericParamDefKind::Type { .. }));
        if has_type_params {
            self.emitter.emit_bool(fn_iri, tg::IS_GENERIC, true);
        }
        self.extract_generics(generics, fn_iri);

        // Parameters
        for (ordinal, (name, ty)) in sig.inputs.iter().enumerate() {
            // Skip `self` parameters (they don't get a separate parameter node)
            if name == "self" {
                continue;
            }

            let param_iri = self.iris.parameter_iri(fn_iri, ordinal);
            self.emitter
                .emit_iri(&param_iri, standard::RDF_TYPE, tg::PARAMETER);
            self.emitter.emit_literal(&param_iri, tg::NAME, name);
            self.emitter
                .emit_int(&param_iri, tg::ORDINAL, ordinal as i64);
            self.emitter
                .emit_iri(fn_iri, tg::HAS_PARAMETER, &param_iri);
            self.emitter
                .emit_iri(&param_iri, tg::PARAMETER_OF, fn_iri);

            if let Some(type_iri) = self.resolve_type_to_iri(ty) {
                self.emitter
                    .emit_iri(&param_iri, tg::PARAMETER_TYPE, &type_iri);
            }
        }

        // Return type
        if let Some(ref ret_type) = sig.output {
            if let Some(type_iri) = self.resolve_type_to_iri(ret_type) {
                self.emitter.emit_iri(fn_iri, tg::RETURN_TYPE, &type_iri);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Error type extraction (Phase 9)
    // -----------------------------------------------------------------------

    fn extract_error_type(&mut self, fn_iri: &str, sig: &FunctionSignature) {
        if let Some(Type::ResolvedPath(ref path)) = sig.output {
            // Check if this is a Result type
            if path.path == "Result" || path.path.ends_with("::Result") {
                if let Some(ref args) = path.args {
                    if let super::rustdoc_model::GenericArgs::AngleBracketed { ref args, .. } =
                        **args
                    {
                        // The second type arg of Result<T, E> is the error type
                        if args.len() >= 2 {
                            if let super::rustdoc_model::GenericArg::Type(ref err_type) = args[1] {
                                if let Some(err_iri) = self.resolve_type_to_iri(err_type) {
                                    self.emitter
                                        .emit_iri(fn_iri, rt::ERROR_TYPE, &err_iri);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // Type resolution (Phase 8)
    // -----------------------------------------------------------------------

    fn resolve_type_to_iri(&mut self, ty: &Type) -> Option<String> {
        match ty {
            Type::ResolvedPath(ref path) => Some(self.resolve_path_to_iri(path)),

            Type::Primitive(ref name) => Some(self.iris.primitive_type_iri(name)),

            Type::Tuple(ref types) => Some(self.iris.tuple_type_iri(types.len())),

            Type::Slice(ref inner) => {
                let elem_name = type_display_name(inner);
                Some(self.iris.slice_type_iri(&elem_name))
            }

            Type::Array {
                ref type_, ref len, ..
            } => {
                let elem_name = type_display_name(type_);
                Some(self.iris.array_type_iri(&elem_name, len))
            }

            Type::RawPointer {
                is_mutable,
                ref type_,
            } => {
                let target_name = type_display_name(type_);
                Some(self.iris.raw_pointer_type_iri(&target_name, *is_mutable))
            }

            Type::BorrowedRef {
                is_mutable,
                ref type_,
                ..
            } => {
                let target_name = type_display_name(type_);
                Some(self.iris.ref_type_iri(&target_name, *is_mutable))
            }

            Type::Generic(_) => {
                // Generic type parameters reference the owner's type parameter.
                // We don't mint a separate IRI for them here.
                None
            }

            Type::ImplTrait(_) | Type::DynTrait(_) | Type::QualifiedPath { .. } => {
                // Complex types — skip for now
                None
            }

            Type::FunctionPointer(_) | Type::Infer | Type::Unknown => None,
        }
    }

    /// Resolve a [`ResolvedPath`] to an IRI.
    fn resolve_path_to_iri(&self, path: &ResolvedPath) -> String {
        // If the item is in our crate's index or paths, build a fully qualified IRI
        if let Some(ref id) = path.id {
            // Check paths first (works for both local and external items)
            if let Some(summary) = self.crate_data.paths.get(&id.0) {
                let full_path = summary.path.join("::");
                return self
                    .iris
                    .type_iri(&self.crate_name, &self.crate_version, &full_path);
            }
            // Check index for local items
            if let Some(item) = self.crate_data.index.get(&id.0) {
                if let Some(ref name) = item.name {
                    return self
                        .iris
                        .type_iri(&self.crate_name, &self.crate_version, name);
                }
            }
        }

        // Fallback: use the path string directly
        self.iris
            .type_iri(&self.crate_name, &self.crate_version, &path.path)
    }

    /// Ensure a type node has been minimally emitted (for external types).
    fn ensure_external_type_emitted(&mut self, type_iri: &str, name: &str) {
        if self.emitted_types.contains(type_iri) {
            return;
        }
        self.emitted_types.insert(type_iri.to_string());
        self.emitter
            .emit_iri(type_iri, standard::RDF_TYPE, tg::TYPE);
        self.emitter.emit_literal(type_iri, tg::NAME, name);
    }
}

// ---------------------------------------------------------------------------
// Free functions
// ---------------------------------------------------------------------------

/// Map a [`Visibility`] to a display string.
fn visibility_str(vis: &Visibility) -> &'static str {
    match vis {
        Visibility::Public => "Public",
        Visibility::Default => "Private",
        Visibility::Crate => "Internal",
        Visibility::Restricted(r) if r.path == "super" => "Protected",
        Visibility::Restricted(_) => "Internal",
    }
}

/// Get a human-readable display name for a type (used for composite type IRIs).
fn type_display_name(ty: &Type) -> String {
    match ty {
        Type::Primitive(name) => name.clone(),
        Type::ResolvedPath(path) => path.path.clone(),
        Type::Generic(name) => name.clone(),
        Type::Tuple(types) => {
            let parts: Vec<String> = types.iter().map(type_display_name).collect();
            format!("({})", parts.join(","))
        }
        Type::Slice(inner) => format!("[{}]", type_display_name(inner)),
        Type::Array { type_, len, .. } => {
            format!("[{};{}]", type_display_name(type_), len)
        }
        Type::BorrowedRef {
            is_mutable, type_, ..
        } => {
            if *is_mutable {
                format!("&mut {}", type_display_name(type_))
            } else {
                format!("&{}", type_display_name(type_))
            }
        }
        Type::RawPointer {
            is_mutable, type_, ..
        } => {
            if *is_mutable {
                format!("*mut {}", type_display_name(type_))
            } else {
                format!("*const {}", type_display_name(type_))
            }
        }
        _ => "unknown".to_string(),
    }
}
