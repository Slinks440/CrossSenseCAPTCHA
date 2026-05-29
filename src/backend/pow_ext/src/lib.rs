use pyo3::prelude::*;
use std::cell::RefCell;

thread_local! {
    static POW_BUFFER: RefCell<Vec<i32>> = RefCell::new(vec![0; 524288]);
}

fn validate_pow_internal(init_seed: &str) -> String {
    let int32_count = 524288;
    
    let mut ptr_final = 0;
    POW_BUFFER.with(|buf_cell| {
        let mut buffer = buf_cell.borrow_mut();
        
        let mut seed: i32 = 0;
        for c in init_seed.chars() {
            seed = seed.wrapping_mul(31).wrapping_add(c as i32);
        }
        
        for i in 0..int32_count {
            seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
            buffer[i] = seed.abs() % (int32_count as i32);
        }
        
        let iter_count = 1_000_000;
        let mut ptr: usize = 0;
        for _ in 0..iter_count {
            ptr = buffer[ptr] as usize;
        }
        ptr_final = ptr;
    });
    
    ptr_final.to_string()
}

#[pyfunction]
fn validate_pow(py: Python, init_seed: &str, _difficulty: u32) -> PyResult<String> {
    let seed_str = init_seed.to_string();
    py.allow_threads(move || {
        Ok(validate_pow_internal(&seed_str))
    })
}

#[pymodule]
fn pow_ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_pow, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pow_deterministic() {
        let seed = "test_seed_123";
        let res1 = validate_pow_internal(seed);
        let res2 = validate_pow_internal(seed);
        assert_eq!(res1, res2, "PoW should be deterministic for the same seed");
    }

    #[test]
    fn test_pow_different_seeds() {
        let res1 = validate_pow_internal("seed_A");
        let res2 = validate_pow_internal("seed_B");
        assert_ne!(res1, res2, "Different seeds should ideally produce different results");
    }
}
