//! A NeXosim mission model on PlanDev's external-model contract, spoken over stdio.
//!
//!     nx-model describe    -> the declaration, as JSON, on stdout
//!     nx-model simulate    <- a normalized request on stdin
//!                          -> {realProfiles, discreteProfiles, spans} on stdout
//!     nx-model validate    <- {subjects:[{type, arguments}]} on stdin
//!                          -> {notices:[[{subjects, message}]]} on stdout
//!
//! The first two verbs are `adapter_core.ExecBackend`'s protocol; the third is not, and is the one
//! thing this model needed that the host did not offer -- see nx_service.py.
//!
//! What is NOT here is the point. There is no HTTP, no `?model=` resolution, no default filling, no
//! ValueSchema typechecker, no identity hash and no response validation, because the Python host
//! does all of it. By the time `simulate` reads stdin, every directive has a declared type, all its
//! required parameters, defaults resolved and every argument checked against the schema `decl.rs`
//! published. Re-implementing any of that here is exactly the drift `adapter_core` was written to
//! stop -- and the same argument holds in Rust, where the second copy would not even be in the same
//! language as the first.
//!
//! Exit 0 succeeded, exit 1 is the model's fault, exit 2 is the caller's. Anything nonzero reaches
//! the operator as a 500 quoting stderr, so the message is the whole diagnosis.

mod decl;
mod model;
mod run;
mod wire;

use std::io::Read;
use wire::Fault;

fn main() {
    let verb = std::env::args().nth(1).unwrap_or_default();
    match dispatch(&verb) {
        Ok(out) => println!("{out}"),
        Err(fault) => {
            eprintln!("{}", fault.message());
            std::process::exit(fault.exit_code());
        }
    }
}

fn dispatch(verb: &str) -> Result<String, Fault> {
    match verb {
        "describe" => Ok(decl::declaration().to_string()),
        "simulate" => {
            let request: wire::Request = serde_json::from_str(&stdin()?)
                .map_err(|e| Fault::Model(format!("could not read the request: {e}")))?;
            let response = run::simulate(&request)?;
            serde_json::to_string(&response)
                .map_err(|e| Fault::Model(format!("could not write the response: {e}")))
        }
        "validate" => {
            let request: wire::ValidateRequest = serde_json::from_str(&stdin()?)
                .map_err(|e| Fault::Model(format!("could not read the request: {e}")))?;
            Ok(run::validate(&request.subjects).to_string())
        }
        other => Err(Fault::Caller(format!(
            "usage: nx-model {{describe|simulate|validate}} (got {other:?})"
        ))),
    }
}

fn stdin() -> Result<String, Fault> {
    let mut buf = String::new();
    std::io::stdin()
        .read_to_string(&mut buf)
        .map_err(|e| Fault::Model(format!("could not read stdin: {e}")))?;
    Ok(buf)
}

#[cfg(test)]
mod tests;
