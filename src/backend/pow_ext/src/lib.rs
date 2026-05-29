use pyo3::prelude::*;
use std::cell::RefCell;

thread_local! {
    static POW_BUFFER: RefCell<Vec<i32>> = RefCell::new(vec![0; 524288]);
}

#[pyfunction]
fn validate_pow(py: Python, init_seed: &str, _difficulty: u32) -> PyResult<String> {
    let seed_str = init_seed.to_string();
    py.allow_threads(move || {
        let int32_count = 524288;
        
        let mut ptr_final = 0;
        POW_BUFFER.with(|buf_cell| {
            let mut buffer = buf_cell.borrow_mut();
            
            // Hash init_seed string into a 32-bit integer just like JS does
            let mut seed: i32 = 0;
            for c in seed_str.chars() {
                seed = seed.wrapping_mul(31).wrapping_add(c as i32);
            }
            
            // Fill buffer deterministically with LCG
            for i in 0..int32_count {
                seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
                buffer[i] = seed.abs() % (int32_count as i32);
            }
            
            // Pointer Chasing
            let iter_count = 1_000_000;
            let mut ptr: usize = 0;
            for _ in 0..iter_count {
                // Safe because the max value is int32_count
                ptr = buffer[ptr] as usize;
            }
            ptr_final = ptr;
        });
        
        Ok(ptr_final.to_string())
    })
}

#[pymodule]
fn pow_ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_pow, m)?)?;
    Ok(())
}
