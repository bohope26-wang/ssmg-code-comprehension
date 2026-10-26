# Unified Criteria for Module Partitioning

### 1. Module Definition

A semantic module is a contiguous region of code within a function whose statements serve the same local semantic goal and collectively perform a coherent processing task. A module typically involves the production, validation, transformation, or use of related data and represents a semantic stage in the function's execution.

### 2. Boundary Identification

Module boundaries are determined primarily by the following factors:

1. **Change in semantic goal:** A transition from input normalization to core computation, or from candidate construction to result aggregation.
2. **Change in the primary object of operation:** A transition from a database collection to a field collection, from a provider to a room, or from a ledger to a bank.
3. **Change in key intermediate artifacts:** Distinct processing stages centered on key data objects such as `allowed_len`, `uri`, `array`, `decision`, `schedule`, `alerts`, or `partition`.
4. **Change in processing paths:** Branches such as sparse/dense, zip/tar, streamed/non-streamed, and receive/reserve/ship that perform distinct processing responsibilities.
5. **Cohesion of validation logic:** Multiple validation conditions belong to the same module when they serve the same stage and jointly determine whether subsequent processing can proceed.
6. **Treatment of return statements:** An ordinary `return` generally belongs to the preceding module, whereas an early return at the function entry or within a branch may form a separate module according to its responsibility.

Boundary decisions should consider semantic goals, primary objects, intermediate artifacts, and control flow together, with an emphasis on identifying distinct processing stages.

### 3. Statement Assignment

- Multiline function calls, dictionary literals, list comprehensions, and string concatenations are assigned according to the processing task they serve.
- Consecutive conditions, validation operations, and filtering logic serving the same goal generally belong to the same module.
- Comments and docstrings remain associated with the corresponding code.
- Temporary variable assignments belong to the processing stage that uses them.
- Updates within a loop that contribute to the same accumulated state belong to the same module.
- Branches, exception handlers, and loops are partitioned according to their semantic responsibilities rather than their syntactic structure alone.

### 4. Module Granularity

Short functions typically contain 4–6 modules, medium-length functions 6–8, and long functions 7–9. These ranges serve as guidelines for partition granularity. The final partition should preserve coherent semantic stages and provide interpretable boundaries, without requiring the same number of modules across functions.
