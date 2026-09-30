{% macro install_stable_hash() %}
-- Freeze DuckDB 1.1.3's UTF-8 MurmurHash64A semantics for seeded decisions.
-- DuckDB's built-in HASH is explicitly version-dependent.
-- Algorithm source: duckdb v1.1.3 src/common/types/hash.cpp (MIT).
-- HashBytes attribution: Copyright (c) 2018-2021 Martin Ankerl.
CREATE OR REPLACE MACRO pa_hash_mul(x) AS
  ((x::UHUGEINT * 14313749767032793493::UHUGEINT) % 18446744073709551616::UHUGEINT)::UBIGINT;
CREATE OR REPLACE MACRO pa_hash_mix(x) AS
  pa_hash_mul(xor(pa_hash_mul(x), pa_hash_mul(x) >> 47));
CREATE OR REPLACE MACRO pa_hash_word(x) AS
  CAST('0x' || array_to_string(list_reverse(regexp_extract_all(x, '..')), '') AS UBIGINT);
CREATE OR REPLACE MACRO pa_hash_finalize(x) AS
  xor(pa_hash_mul(xor(x, x >> 47)), pa_hash_mul(xor(x, x >> 47)) >> 47);
CREATE OR REPLACE MACRO pa_hash_blocks(x) AS
  list_reduce(
    list_concat(
      [xor(3782874213::UBIGINT, pa_hash_mul(length(x) // 2))],
      list_transform(range(length(x) // 16), i -> pa_hash_mix(pa_hash_word(substr(x, i * 16 + 1, 16))))
    ),
    (a, b) -> pa_hash_mul(xor(a, b))
  );
CREATE OR REPLACE MACRO pa_hash_hex(x) AS
  pa_hash_finalize(CASE WHEN length(x) % 16 = 0 THEN pa_hash_blocks(x)
    ELSE pa_hash_mul(xor(pa_hash_blocks(x), pa_hash_word(substr(x, (length(x) // 16) * 16 + 1)))) END);
CREATE OR REPLACE MACRO planalign_hash(x) AS
  CASE WHEN x IS NULL THEN 13787848793156543929::UBIGINT ELSE pa_hash_hex(hex(encode(x::VARCHAR))) END;
{% endmacro %}
