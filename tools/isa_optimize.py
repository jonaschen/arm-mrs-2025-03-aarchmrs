#!/usr/bin/env python3
"""
isa_optimize.py — Advanced ISA optimization for AArch64 (SVE2/SME/PAC/BTI/MTE).

Generates high-performance and security-hardened AArch64 code using the latest
ISA extensions.  Feature gating is enforced through the H1 allowlist API so
that generated code only uses instructions available at the target architecture
version.

Usage:
    isa_optimize.py --list-templates [--category CATEGORY]
    isa_optimize.py --template NAME --arch VERSION [--output json]
    isa_optimize.py --auto-pac-bti --arch VERSION --input FILE
    isa_optimize.py --mte-helpers --arch VERSION
    isa_optimize.py --list-rules [--category CATEGORY]
    isa_optimize.py --check-features --arch VERSION [--feat FEAT_X ...]

Environment:
    ARM_MRS_CACHE_DIR  Override cache directory (default: <repo_root>/cache)

Exit codes:
    0  success
    1  invalid arguments, feature not available, or missing cache
"""

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Import H1 (query_allowlist) and H5 (arch_to_march_flag) APIs
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent.resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from query_allowlist import (          # noqa: E402
    VERSION_ORDER,
    VERSION_SET,
    features_for_arch,
    load_features,
    query_allowlist,
)
from setup_cross_compile import (      # noqa: E402
    arch_to_march_flag,
)

SCHEMA_VERSION = '1.0'

# ---------------------------------------------------------------------------
# Architecture version helpers (re-used from H1)
# ---------------------------------------------------------------------------

VERSION_INDEX = {v: i for i, v in enumerate(VERSION_ORDER)}


def _version_ge(arch: str, min_ver: str) -> bool:
    """Return True if *arch* >= *min_ver* in VERSION_ORDER."""
    return VERSION_INDEX.get(arch, -1) >= VERSION_INDEX.get(min_ver, 999)


# ---------------------------------------------------------------------------
# Feature availability helpers (powered by H1)
# ---------------------------------------------------------------------------

# Map from extension name to the feature flag and the minimum arch version
# where the feature was architecturally mandated.  The min_arch value is only
# used for user-friendly messaging; actual gating goes through H1.
_EXTENSION_INFO: dict[str, dict] = {
    'SVE2': {
        'features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'march_ext': '+sve2',
        'description': 'Scalable Vector Extension v2 (variable-length SIMD)',
    },
    'SME': {
        'features': ['FEAT_SME'],
        'min_arch': 'v9Ap2',
        'march_ext': '+sme',
        'description': 'Scalable Matrix Extension (outer-product acceleration)',
    },
    'PAC': {
        'features': ['FEAT_PAuth'],
        'min_arch': 'v8Ap3',
        'march_ext': '+pauth',
        'description': 'Pointer Authentication (return-address signing)',
    },
    'BTI': {
        'features': ['FEAT_BTI'],
        'min_arch': 'v8Ap5',
        'march_ext': '+bti',
        'description': 'Branch Target Identification (indirect-branch hardening)',
    },
    'MTE': {
        'features': ['FEAT_MTE'],
        'min_arch': 'v8Ap5',
        'march_ext': '+memtag',
        'description': 'Memory Tagging Extension (heap-safety tagging)',
    },
}


def check_extension_available(arch: str, ext_name: str) -> tuple:
    """
    Check whether an ISA extension is available at *arch*.

    Returns (available: bool, detail: str).
    """
    info = _EXTENSION_INFO.get(ext_name.upper())
    if info is None:
        return False, f"Unknown extension '{ext_name}'"

    feats = info['features']
    features_cache = load_features()
    active = features_for_arch(arch, features_cache)

    for feat in feats:
        if feat not in active:
            return (
                False,
                f"{ext_name} requires {feat} (available at {info['min_arch']}+, "
                f"target is {arch})"
            )
    return True, f'{ext_name} is available at {arch}'


def check_features(arch: str, feat_names: list) -> dict:
    """
    Programmatic feature availability check.

    Returns dict with per-extension status and the overall result.
    """
    results = {}
    all_ok = True
    for name in feat_names:
        ok, detail = check_extension_available(arch, name)
        results[name] = {'available': ok, 'detail': detail}
        if not ok:
            all_ok = False
    return {
        'arch': arch,
        'all_available': all_ok,
        'extensions': results,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SVE2 / SME TEMPLATES  (H6-1)
# ═══════════════════════════════════════════════════════════════════════════

_SVE2_TEMPLATES: dict[str, dict] = {
    'sve2-dotproduct': {
        'category': 'sve2',
        'description': 'SVE2 integer dot-product accumulation loop',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 dot-product: dst[i] += a[i] * b[i] (int8 → int32)
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>
            #include <stdint.h>

            void sve2_dotprod(int32_t *dst, const int8_t *a,
                              const int8_t *b, int n) {{
                int i = 0;
                svbool_t pg = svwhilelt_b32(i, n);
                do {{
                    svint32_t acc = svld1_s32(pg, dst + i);
                    svint8_t  va  = svld1_s8(svwhilelt_b8(i * 4, n * 4), a + i * 4);
                    svint8_t  vb  = svld1_s8(svwhilelt_b8(i * 4, n * 4), b + i * 4);
                    acc = svdot_s32(acc, va, vb);
                    svst1_s32(pg, dst + i, acc);
                    i += svcntw();
                    pg = svwhilelt_b32(i, n);
                }} while (svptest_any(svptrue_b32(), pg));
            }}
        """),
    },
    'sve2-matrix-multiply': {
        'category': 'sve2',
        'description': 'SVE2 integer matrix multiply (SMMLA)',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 matrix multiply: C += A * B (int8 → int32 tile)
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>
            #include <stdint.h>

            void sve2_matmul_tile(int32_t *C, const int8_t *A,
                                  const int8_t *B, int M, int N, int K) {{
                for (int i = 0; i < M; i++) {{
                    int j = 0;
                    svbool_t pg = svwhilelt_b32(j, N);
                    do {{
                        svint32_t acc = svld1_s32(pg, C + i * N + j);
                        for (int k = 0; k < K; k += 8) {{
                            svint8_t va = svld1_s8(svwhilelt_b8(0, K - k), A + i * K + k);
                            svint8_t vb = svld1_s8(svwhilelt_b8(0, K - k), B + j * K + k);
                            acc = svdot_s32(acc, va, vb);
                        }}
                        svst1_s32(pg, C + i * N + j, acc);
                        j += svcntw();
                        pg = svwhilelt_b32(j, N);
                    }} while (svptest_any(svptrue_b32(), pg));
                }}
            }}
        """),
    },
    'sve2-convolution': {
        'category': 'sve2',
        'description': 'SVE2 1-D convolution with predicated load/store',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 1-D convolution: out[i] = sum_k(in[i+k] * kernel[k])
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>

            void sve2_conv1d(float *out, const float *in, const float *kernel,
                             int n, int ksize) {{
                for (int i = 0; i < n - ksize + 1; i++) {{
                    svfloat32_t acc = svdup_f32(0.0f);
                    for (int k = 0; k < ksize; k++) {{
                        int j = 0;
                        svbool_t pg = svwhilelt_b32(j, 1);
                        svfloat32_t vin = svld1_s32(pg, (const int32_t *)(in + i + k));
                        svfloat32_t vk  = svdup_f32(kernel[k]);
                        acc = svmla_f32_m(pg, acc, vin, vk);
                    }}
                    svst1_f32(svwhilelt_b32(0, 1), out + i, acc);
                }}
            }}
        """),
    },
    'sve2-reduce': {
        'category': 'sve2',
        'description': 'SVE2 horizontal reduction (sum)',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 horizontal sum: return sum(arr[0..n-1])
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>

            float sve2_reduce_sum(const float *arr, int n) {{
                int i = 0;
                svfloat32_t acc = svdup_f32(0.0f);
                svbool_t pg = svwhilelt_b32(i, n);
                do {{
                    svfloat32_t v = svld1_f32(pg, arr + i);
                    acc = svadd_f32_m(pg, acc, v);
                    i += svcntw();
                    pg = svwhilelt_b32(i, n);
                }} while (svptest_any(svptrue_b32(), pg));
                return svaddv_f32(svptrue_b32(), acc);
            }}
        """),
    },
    'sve2-gather': {
        'category': 'sve2',
        'description': 'SVE2 gather-load from index array',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 gather load: dst[i] = src[idx[i]]
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>
            #include <stdint.h>

            void sve2_gather(int32_t *dst, const int32_t *src,
                             const uint32_t *idx, int n) {{
                int i = 0;
                svbool_t pg = svwhilelt_b32(i, n);
                do {{
                    svuint32_t vidx = svld1_u32(pg, idx + i);
                    svint32_t  val  = svld1_gather_u32index_s32(pg, src, vidx);
                    svst1_s32(pg, dst + i, val);
                    i += svcntw();
                    pg = svwhilelt_b32(i, n);
                }} while (svptest_any(svptrue_b32(), pg));
            }}
        """),
    },
    'sve2-scatter': {
        'category': 'sve2',
        'description': 'SVE2 scatter-store to index array',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 scatter store: dst[idx[i]] = src[i]
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>
            #include <stdint.h>

            void sve2_scatter(int32_t *dst, const int32_t *src,
                              const uint32_t *idx, int n) {{
                int i = 0;
                svbool_t pg = svwhilelt_b32(i, n);
                do {{
                    svint32_t  val  = svld1_s32(pg, src + i);
                    svuint32_t vidx = svld1_u32(pg, idx + i);
                    svst1_scatter_u32index_s32(pg, dst, vidx, val);
                    i += svcntw();
                    pg = svwhilelt_b32(i, n);
                }} while (svptest_any(svptrue_b32(), pg));
            }}
        """),
    },
    'sve2-scan': {
        'category': 'sve2',
        'description': 'SVE2 prefix-sum (inclusive scan)',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 inclusive prefix sum: out[i] = sum(in[0..i])
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>

            void sve2_prefix_sum(float *out, const float *in, int n) {{
                float carry = 0.0f;
                int i = 0;
                svbool_t pg = svwhilelt_b32(i, n);
                do {{
                    svfloat32_t v = svld1_f32(pg, in + i);
                    /* Intra-vector prefix sum via shift-and-add */
                    svfloat32_t s = v;
                    s = svadd_f32_m(pg, s, svext_f32(svdup_f32(0.0f), s, svcntw() - 1));
                    /* Add inter-lane carry */
                    s = svadd_f32_x(pg, s, svdup_f32(carry));
                    svst1_f32(pg, out + i, s);
                    carry = svlasta_f32(pg, s);
                    i += svcntw();
                    pg = svwhilelt_b32(i, n);
                }} while (svptest_any(svptrue_b32(), pg));
            }}
        """),
    },
    'sve2-permute': {
        'category': 'sve2',
        'description': 'SVE2 table-lookup permutation (TBL)',
        'required_features': ['FEAT_SVE2'],
        'min_arch': 'v9Ap0',
        'code': textwrap.dedent("""\
            /* SVE2 vector permutation via TBL
             * Compile: {march_flag}
             * Requires: FEAT_SVE2
             */
            #include <arm_sve.h>
            #include <stdint.h>

            void sve2_permute(uint8_t *dst, const uint8_t *src,
                              const uint8_t *perm, int n) {{
                int i = 0;
                svbool_t pg = svwhilelt_b8(i, n);
                do {{
                    svuint8_t vsrc  = svld1_u8(pg, src + i);
                    svuint8_t vperm = svld1_u8(pg, perm + i);
                    svuint8_t vout  = svtbl_u8(vsrc, vperm);
                    svst1_u8(pg, dst + i, vout);
                    i += svcntb();
                    pg = svwhilelt_b8(i, n);
                }} while (svptest_any(svptrue_b8(), pg));
            }}
        """),
    },
}

_SME_TEMPLATES: dict[str, dict] = {
    'sme-matmul': {
        'category': 'sme',
        'description': 'SME outer-product matrix multiply (FP32 tiles)',
        'required_features': ['FEAT_SME'],
        'min_arch': 'v9Ap2',
        'code': textwrap.dedent("""\
            /* SME matrix multiply using streaming SVE + outer products
             * Compile: {march_flag}
             * Requires: FEAT_SME
             */
            #include <arm_sme.h>
            #include <arm_sve.h>

            __arm_new("za") void sme_matmul(float *C, const float *A,
                                             const float *B, int M, int N, int K) {{
                svzero_za();
                for (int i = 0; i < M; i++) {{
                    for (int k = 0; k < K; k++) {{
                        svfloat32_t va = svdup_f32(A[i * K + k]);
                        svbool_t pg = svwhilelt_b32(0, N);
                        svfloat32_t vb = svld1_f32(pg, B + k * N);
                        svmopa_za32_f32_m(0, svptrue_b32(), pg, va, vb);
                    }}
                }}
                /* Store ZA tile row by row to C */
                for (int i = 0; i < M; i++) {{
                    svbool_t pg = svwhilelt_b32(0, N);
                    svfloat32_t row;
                    svread_za32_f32_m(row, pg, 0, i);
                    svst1_f32(pg, C + i * N, row);
                }}
            }}
        """),
    },
    'sme-accumulate': {
        'category': 'sme',
        'description': 'SME streaming-mode accumulation',
        'required_features': ['FEAT_SME'],
        'min_arch': 'v9Ap2',
        'code': textwrap.dedent("""\
            /* SME streaming accumulate: ZA += outer(a, b)
             * Compile: {march_flag}
             * Requires: FEAT_SME
             */
            #include <arm_sme.h>
            #include <arm_sve.h>

            __arm_new("za") void sme_accumulate(float *out, const float *a,
                                                 const float *b, int n) {{
                svzero_za();
                svbool_t pg = svwhilelt_b32(0, n);
                svfloat32_t va = svld1_f32(pg, a);
                svfloat32_t vb = svld1_f32(pg, b);
                svmopa_za32_f32_m(0, pg, pg, va, vb);
                /* Read-back first row as demo */
                svfloat32_t row;
                svread_za32_f32_m(row, pg, 0, 0);
                svst1_f32(pg, out, row);
            }}
        """),
    },
    'sme-transpose': {
        'category': 'sme',
        'description': 'SME ZA tile transpose',
        'required_features': ['FEAT_SME'],
        'min_arch': 'v9Ap2',
        'code': textwrap.dedent("""\
            /* SME tile transpose via ZA read/write
             * Compile: {march_flag}
             * Requires: FEAT_SME
             */
            #include <arm_sme.h>
            #include <arm_sve.h>
            #include <stdint.h>

            __arm_new("za") void sme_transpose(float *dst, const float *src,
                                                int rows, int cols) {{
                svzero_za();
                /* Load rows into ZA tile */
                for (int r = 0; r < rows; r++) {{
                    svbool_t pg = svwhilelt_b32(0, cols);
                    svfloat32_t row = svld1_f32(pg, src + r * cols);
                    svwrite_za32_f32_m(0, r, pg, row);
                }}
                /* Read columns out as rows of the transposed result */
                for (int c = 0; c < cols; c++) {{
                    svbool_t pg = svwhilelt_b32(0, rows);
                    svfloat32_t col;
                    svread_za32_f32_m(col, pg, 0, c);
                    svst1_f32(pg, dst + c * rows, col);
                }}
            }}
        """),
    },
    'sme-int8-matmul': {
        'category': 'sme',
        'description': 'SME int8 matrix multiply (int8 → int32 tiles)',
        'required_features': ['FEAT_SME'],
        'min_arch': 'v9Ap2',
        'code': textwrap.dedent("""\
            /* SME int8 → int32 matrix multiply using SMOPA
             * Compile: {march_flag}
             * Requires: FEAT_SME
             */
            #include <arm_sme.h>
            #include <arm_sve.h>
            #include <stdint.h>

            __arm_new("za") void sme_int8_matmul(int32_t *C, const int8_t *A,
                                                  const int8_t *B, int M, int N, int K) {{
                svzero_za();
                for (int i = 0; i < M; i++) {{
                    for (int k = 0; k < K; k += 4) {{
                        svbool_t pg8 = svwhilelt_b8(0, N * 4);
                        svint8_t va = svld1_s8(svwhilelt_b8(0, K - k), A + i * K + k);
                        svint8_t vb = svld1_s8(pg8, B + k * N);
                        svsmopa_za32_s8_m(0, svptrue_b8(), pg8, va, vb);
                    }}
                }}
                for (int i = 0; i < M; i++) {{
                    svbool_t pg = svwhilelt_b32(0, N);
                    svint32_t row;
                    svread_za32_s32_m(row, pg, 0, i);
                    svst1_s32(pg, C + i * N, row);
                }}
            }}
        """),
    },
}

ALL_TEMPLATES: dict[str, dict] = {**_SVE2_TEMPLATES, **_SME_TEMPLATES}


def list_templates(category: str | None = None) -> list:
    """Return a list of template dicts with name, category, description."""
    result = []
    for name, tmpl in ALL_TEMPLATES.items():
        if category and tmpl['category'] != category:
            continue
        result.append({
            'name': name,
            'category': tmpl['category'],
            'description': tmpl['description'],
            'required_features': tmpl['required_features'],
            'min_arch': tmpl['min_arch'],
        })
    return sorted(result, key=lambda t: (t['category'], t['name']))


def generate_template(name: str, arch: str) -> dict:
    """
    Generate a code template for the given architecture.

    Returns dict with keys: name, arch, march_flag, code, features_used.
    Raises ValueError if template not found or features not available.
    """
    tmpl = ALL_TEMPLATES.get(name)
    if tmpl is None:
        available = ', '.join(sorted(ALL_TEMPLATES.keys()))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")

    # Check feature availability via H1
    for feat in tmpl['required_features']:
        ok, detail = check_extension_available(arch, _feat_to_ext_name(feat))
        if not ok:
            raise ValueError(
                f"Template '{name}' requires {feat} which is not available at "
                f"{arch}. {detail}"
            )

    march_flag = arch_to_march_flag(arch, tmpl['required_features'])
    code = tmpl['code'].format(march_flag=march_flag)

    return {
        'schema_version': SCHEMA_VERSION,
        'name': name,
        'arch': arch,
        'category': tmpl['category'],
        'description': tmpl['description'],
        'march_flag': march_flag,
        'required_features': tmpl['required_features'],
        'code': code,
    }


def _feat_to_ext_name(feat: str) -> str:
    """Map FEAT_* name to extension name (SVE2, SME, PAC, BTI, MTE)."""
    _MAP = {
        'FEAT_SVE2': 'SVE2',
        'FEAT_SME': 'SME',
        'FEAT_PAuth': 'PAC',
        'FEAT_BTI': 'BTI',
        'FEAT_MTE': 'MTE',
    }
    return _MAP.get(feat, feat)


# ═══════════════════════════════════════════════════════════════════════════
# PAC / BTI AUTO-INSERTION  (H6-2)
# ═══════════════════════════════════════════════════════════════════════════

def insert_pac_bti(asm_text: str, arch: str) -> dict:
    """
    Auto-insert PAC and/or BTI instructions into AArch64 assembly.

    Rules:
      - PAC (PACIASP / AUTIASP): inserted if FEAT_PAuth is available (v8Ap3+)
      - BTI (BTI c): inserted at function entry if FEAT_BTI is available (v8Ap5+)

    Returns dict with keys: arch, pac_available, bti_available,
        original_functions, hardened_functions, output.
    """
    features_cache = load_features()
    active = features_for_arch(arch, features_cache)

    pac_available = 'FEAT_PAuth' in active
    bti_available = 'FEAT_BTI' in active

    lines = asm_text.splitlines(keepends=True)
    output_lines = []
    func_count = 0
    hardened_count = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect function entry: a global label followed by instructions
        # Pattern: <name>:  (at start of line, not indented, not a directive)
        if (re.match(r'^[a-zA-Z_]\w*:', stripped)
                and not stripped.startswith('.')
                and not stripped.startswith('//')):
            func_count += 1
            output_lines.append(line)
            i += 1
            # Insert hardening instructions after the label
            inserted = []
            if bti_available:
                inserted.append('\tbti\tc\n')
            if pac_available:
                inserted.append('\tpaciasp\n')
            if inserted:
                hardened_count += 1
                output_lines.extend(inserted)
            continue

        # Detect function return: `ret` instruction
        if stripped == 'ret' or stripped.startswith('ret '):
            if pac_available:
                output_lines.append('\tautiasp\n')
            output_lines.append(line)
            i += 1
            continue

        output_lines.append(line)
        i += 1

    return {
        'arch': arch,
        'pac_available': pac_available,
        'bti_available': bti_available,
        'original_functions': func_count,
        'hardened_functions': hardened_count,
        'output': ''.join(output_lines),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MTE TAG-MANAGEMENT HELPERS  (H6-3)
# ═══════════════════════════════════════════════════════════════════════════

def generate_mte_helpers(arch: str) -> dict:
    """
    Generate MTE (Memory Tagging Extension) helper code.

    Returns dict with arch, available, march_flag, helpers.
    Raises ValueError if MTE is not available at the target arch.
    """
    ok, detail = check_extension_available(arch, 'MTE')
    if not ok:
        raise ValueError(detail)

    march_flag = arch_to_march_flag(arch, ['FEAT_MTE'])

    helpers = textwrap.dedent("""\
        /* MTE tag-management helpers
         * Compile: {march_flag}
         * Requires: FEAT_MTE (ARMv8.5-A+)
         */
        #ifndef MTE_HELPERS_H
        #define MTE_HELPERS_H

        #include <arm_acle.h>
        #include <stddef.h>
        #include <stdint.h>

        /* IRG — Insert Random Tag: create a tagged pointer from an untagged base.
         * The hardware generates a random 4-bit tag in bits [59:56].
         */
        static inline void *mte_create_tag(void *ptr, uint64_t exclude_mask) {{
            return __arm_mte_create_random_tag(ptr, exclude_mask);
        }}

        /* STG — Store Allocation Tag: write the tag from a tagged pointer
         * into the tag memory for a 16-byte granule.
         */
        static inline void mte_set_tag(void *tagged_ptr) {{
            __arm_mte_set_tag(tagged_ptr);
        }}

        /* LDG — Load Allocation Tag: read the tag from tag memory
         * and return a pointer with that tag in bits [59:56].
         */
        static inline void *mte_get_tag(void *ptr) {{
            return __arm_mte_get_tag(ptr);
        }}

        /* ADDG — Add Scaled Immediate to Tag: adjust pointer tag by offset.
         * Useful for sub-object tagging within a single allocation.
         */
        static inline void *mte_increment_tag(void *ptr, unsigned tag_offset) {{
            return __arm_mte_increment_tag(ptr, tag_offset);
        }}

        /* Tag a contiguous memory region (granule by granule).
         * size must be a multiple of 16 (MTE granule size).
         */
        static inline void *mte_tag_region(void *ptr, size_t size) {{
            void *tagged = mte_create_tag(ptr, 0);
            for (size_t off = 0; off < size; off += 16) {{
                mte_set_tag((char *)tagged + off);
            }}
            return tagged;
        }}

        /* Allocate and tag a memory pool.
         * Returns a tagged pointer; caller frees with the original
         * (untagged) base from the allocator.
         */
        static inline void *mte_alloc_pool(void *base, size_t pool_size) {{
            return mte_tag_region(base, pool_size);
        }}

        #endif /* MTE_HELPERS_H */
    """).format(march_flag=march_flag)

    return {
        'schema_version': SCHEMA_VERSION,
        'arch': arch,
        'available': True,
        'march_flag': march_flag,
        'helpers': helpers,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY BEST-PRACTICE RULES  (H6-4)
# ═══════════════════════════════════════════════════════════════════════════

SECURITY_RULES: list[dict] = [
    # PAC rules (R01–R05)
    {
        'id': 'R01',
        'category': 'pac',
        'title': 'Sign return address in function prologue',
        'description': 'Every non-leaf function must sign its return address with '
                       'PACIASP in the prologue to prevent ROP attacks.',
        'instruction': 'PACIASP',
        'min_arch': 'v8Ap3',
        'required_features': ['FEAT_PAuth'],
    },
    {
        'id': 'R02',
        'category': 'pac',
        'title': 'Authenticate return address before RET',
        'description': 'Every function that signs its return address must '
                       'authenticate with AUTIASP before the RET instruction.',
        'instruction': 'AUTIASP',
        'min_arch': 'v8Ap3',
        'required_features': ['FEAT_PAuth'],
    },
    {
        'id': 'R03',
        'category': 'pac',
        'title': 'PAC key diversity',
        'description': 'Use IA-key for return addresses and IB/DA/DB keys for '
                       'data pointers to limit key reuse across domains.',
        'instruction': 'PACIBSP / PACDA / PACDB',
        'min_arch': 'v8Ap3',
        'required_features': ['FEAT_PAuth'],
    },
    {
        'id': 'R04',
        'category': 'pac',
        'title': 'No unauthenticated pointer dereference after load',
        'description': 'Never dereference a function pointer loaded from memory '
                       'without first authenticating it (AUT*).',
        'instruction': 'AUTIA / AUTIB / AUTDA / AUTDB',
        'min_arch': 'v8Ap3',
        'required_features': ['FEAT_PAuth'],
    },
    {
        'id': 'R05',
        'category': 'pac',
        'title': 'Use RETAA/RETAB where available',
        'description': 'On Armv8.3+ use combined authenticate-and-return '
                       'instructions (RETAA/RETAB) to reduce gadget opportunities.',
        'instruction': 'RETAA / RETAB',
        'min_arch': 'v8Ap3',
        'required_features': ['FEAT_PAuth'],
    },
    # BTI rules (R06–R10)
    {
        'id': 'R06',
        'category': 'bti',
        'title': 'BTI landing pad at every indirect branch target',
        'description': 'All functions reachable via indirect call (function '
                       'pointers, PLT, vtables) must start with BTI c or BTI jc.',
        'instruction': 'BTI c',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_BTI'],
    },
    {
        'id': 'R07',
        'category': 'bti',
        'title': 'BTI j at indirect jump targets',
        'description': 'Code reached via indirect jumps (BR Xn) must have BTI j.',
        'instruction': 'BTI j',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_BTI'],
    },
    {
        'id': 'R08',
        'category': 'bti',
        'title': 'Enable GP bit in page tables for BTI enforcement',
        'description': 'BTI is enforced only when the Guarded Page (GP) attribute '
                       'is set in the translation table entry. Ensure the OS/loader '
                       'marks code pages with GP=1.',
        'instruction': 'N/A (page table configuration)',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_BTI'],
    },
    {
        'id': 'R09',
        'category': 'bti',
        'title': 'Combine PAC + BTI at function entry',
        'description': 'PACIASP acts as a BTI c landing pad on Armv8.5+. Use '
                       'PACIASP as the first instruction (replaces separate BTI c) '
                       'when both PAC and BTI are available.',
        'instruction': 'PACIASP (implicit BTI c)',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_PAuth', 'FEAT_BTI'],
    },
    {
        'id': 'R10',
        'category': 'bti',
        'title': 'No computed branch into mid-function code',
        'description': 'Indirect branches must land on BTI-marked sites; jumping '
                       'into the middle of a function body without a BTI instruction '
                       'triggers a Branch Target Exception.',
        'instruction': 'BTI c / BTI j / BTI jc',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_BTI'],
    },
    # MTE rules (R11–R15)
    {
        'id': 'R11',
        'category': 'mte',
        'title': 'Tag every heap allocation',
        'description': 'Use IRG + STG to assign a random tag to every heap '
                       'allocation. This detects use-after-free and buffer '
                       'overflows at the granule boundary.',
        'instruction': 'IRG / STG',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE'],
    },
    {
        'id': 'R12',
        'category': 'mte',
        'title': 'Align allocations to 16-byte MTE granule',
        'description': 'MTE operates on 16-byte granules. All tagged allocations '
                       'must be 16-byte aligned, and sizes rounded up to 16.',
        'instruction': 'STG / ST2G',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE'],
    },
    {
        'id': 'R13',
        'category': 'mte',
        'title': 'Clear tags on free',
        'description': 'When freeing memory, clear the allocation tag (set to '
                       'tag 0) with STG to prevent stale-tag reuse.',
        'instruction': 'STG (tag=0)',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE'],
    },
    {
        'id': 'R14',
        'category': 'mte',
        'title': 'Enable tag checking in SCTLR_EL1.TCF',
        'description': 'MTE tag checks are controlled by SCTLR_EL1.TCF0 (EL0) '
                       'and SCTLR_EL1.TCF (EL1). Set to synchronous mode (0b01) '
                       'for deterministic fault detection.',
        'instruction': 'MSR SCTLR_EL1 (TCF bits)',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE'],
    },
    {
        'id': 'R15',
        'category': 'mte',
        'title': 'Use ADDG for sub-object tagging',
        'description': 'Within a single allocation, use ADDG to assign distinct '
                       'tags to sub-objects (e.g. struct members) for finer-grained '
                       'spatial safety.',
        'instruction': 'ADDG',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE'],
    },
    # General security rules (R16–R18)
    {
        'id': 'R16',
        'category': 'general',
        'title': 'Stack tagging with MTE',
        'description': 'Use FEAT_MTE2 stack tagging (if available) to protect '
                       'stack buffers. The compiler inserts IRG/STG around stack '
                       'allocations with -fsanitize=memtag-stack.',
        'instruction': 'IRG / STG (stack)',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_MTE2'],
    },
    {
        'id': 'R17',
        'category': 'general',
        'title': 'Combine PAC + BTI + MTE for defense in depth',
        'description': 'Enable all three security extensions together: PAC for '
                       'control-flow integrity, BTI for indirect-branch '
                       'protection, MTE for memory safety. Compile with '
                       '-mbranch-protection=standard -fsanitize=memtag-heap.',
        'instruction': 'PACIASP / BTI c / IRG / STG',
        'min_arch': 'v8Ap5',
        'required_features': ['FEAT_PAuth', 'FEAT_BTI', 'FEAT_MTE'],
    },
    {
        'id': 'R18',
        'category': 'general',
        'title': 'Prefer FEAT_PAuth2 enhanced PAC when available',
        'description': 'FEAT_PAuth2 (Armv8.6+) adds enhanced PAC with larger '
                       'signature space and FPAC fault-on-failure. Target v8Ap6+ '
                       'for stronger PAC guarantees.',
        'instruction': 'PACIASP (enhanced)',
        'min_arch': 'v8Ap6',
        'required_features': ['FEAT_PAuth2'],
    },
]


def list_security_rules(category: str | None = None) -> list:
    """Return security rules, optionally filtered by category."""
    if category:
        return [r for r in SECURITY_RULES if r['category'] == category]
    return list(SECURITY_RULES)


# ═══════════════════════════════════════════════════════════════════════════
# CLI COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

def cmd_list_templates(category: str | None, output: str) -> int:
    """List all available templates."""
    templates = list_templates(category)
    if not templates:
        cat_hint = f" in category '{category}'" if category else ''
        print(f'No templates found{cat_hint}.', file=sys.stderr)
        print(f'Available categories: sve2, sme', file=sys.stderr)
        return 1

    if output == 'json':
        print(json.dumps({'templates': templates}, indent=2))
        return 0

    hdr = 'Available code-generation templates'
    if category:
        hdr += f' (category: {category})'
    print(hdr)
    print('-' * 60)
    for t in templates:
        feats = ', '.join(t['required_features'])
        print(f"  {t['name']:30s}  {t['description']}")
        print(f"  {'':30s}  requires: {feats}  (min {t['min_arch']})")
    print()
    print(f'Templates: {len(templates)}')
    return 0


def cmd_generate_template(name: str, arch: str, output: str) -> int:
    """Generate a specific template for the given arch."""
    try:
        result = generate_template(name, arch)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1

    if output == 'json':
        print(json.dumps(result, indent=2))
    else:
        print(f'/* Template: {result["name"]}')
        print(f' * Arch: {result["arch"]}')
        print(f' * Compile: {result["march_flag"]}')
        print(f' * Features: {", ".join(result["required_features"])}')
        print(f' */')
        print()
        print(result['code'])
    return 0


def cmd_auto_pac_bti(arch: str, input_file: str | None, output: str) -> int:
    """Insert PAC/BTI instructions into assembly."""
    if input_file:
        try:
            asm_text = Path(input_file).read_text()
        except FileNotFoundError:
            print(f"ERROR: File not found: {input_file}", file=sys.stderr)
            return 1
    else:
        # Read from stdin
        asm_text = sys.stdin.read()

    result = insert_pac_bti(asm_text, arch)

    if output == 'json':
        print(json.dumps(result, indent=2))
    else:
        print(f'// PAC available: {result["pac_available"]}')
        print(f'// BTI available: {result["bti_available"]}')
        print(f'// Functions found: {result["original_functions"]}')
        print(f'// Functions hardened: {result["hardened_functions"]}')
        print()
        print(result['output'])
    return 0


def cmd_mte_helpers(arch: str, output: str) -> int:
    """Generate MTE helper code."""
    try:
        result = generate_mte_helpers(arch)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1

    if output == 'json':
        print(json.dumps(result, indent=2))
    else:
        print(result['helpers'])
    return 0


def cmd_list_rules(category: str | None, output: str) -> int:
    """List security best-practice rules."""
    rules = list_security_rules(category)

    if output == 'json':
        print(json.dumps({'rules': rules, 'count': len(rules)}, indent=2))
        return 0

    hdr = 'Security best-practice rules'
    if category:
        hdr += f' (category: {category})'
    print(hdr)
    print('-' * 60)
    for r in rules:
        feats = ', '.join(r['required_features'])
        print(f"  [{r['id']}] {r['title']}")
        print(f"         {r['description']}")
        print(f"         instruction: {r['instruction']}  |  "
              f"min: {r['min_arch']}  |  requires: {feats}")
        print()
    print(f'Rules: {len(rules)}')
    return 0


def cmd_check_features(arch: str, feat_names: list, output: str) -> int:
    """Check feature availability at the target architecture."""
    # Map short extension names to the check
    ext_names = []
    for name in feat_names:
        # Accept both 'SVE2' and 'FEAT_SVE2' forms
        upper = name.upper()
        if upper in _EXTENSION_INFO:
            ext_names.append(upper)
        elif upper.startswith('FEAT_'):
            mapped = _feat_to_ext_name(upper)
            if mapped in _EXTENSION_INFO:
                ext_names.append(mapped)
            else:
                ext_names.append(upper)
        else:
            ext_names.append(upper)

    result = check_features(arch, ext_names)

    if output == 'json':
        print(json.dumps(result, indent=2))
        return 0

    print(f'Feature availability at {arch}')
    print('-' * 50)
    for name, info in result['extensions'].items():
        status = '✓ available' if info['available'] else '✗ NOT available'
        print(f'  {name:8s}  {status}')
        if not info['available']:
            print(f'  {"":8s}  {info["detail"]}')
    print()
    all_status = 'ALL AVAILABLE' if result['all_available'] else 'SOME UNAVAILABLE'
    print(f'Result: {all_status}')

    return 0 if result['all_available'] else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Advanced ISA optimization for AArch64 (SVE2/SME/PAC/BTI/MTE).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              isa_optimize.py --list-templates
              isa_optimize.py --list-templates --category sve2
              isa_optimize.py --template sve2-dotproduct --arch v9Ap4
              isa_optimize.py --template sme-matmul --arch v9Ap2 --output json
              isa_optimize.py --auto-pac-bti --arch v9Ap0 --input func.s
              isa_optimize.py --mte-helpers --arch v8Ap5
              isa_optimize.py --list-rules --category pac
              isa_optimize.py --check-features --arch v9Ap4 SVE2 SME MTE
        """),
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--list-templates', action='store_true',
                       help='List available code-generation templates.')
    group.add_argument('--template', metavar='NAME',
                       help='Generate a specific template (e.g. sve2-dotproduct).')
    group.add_argument('--auto-pac-bti', action='store_true',
                       help='Auto-insert PAC/BTI into assembly source.')
    group.add_argument('--mte-helpers', action='store_true',
                       help='Generate MTE tag-management helper header.')
    group.add_argument('--list-rules', action='store_true',
                       help='List security best-practice rules.')
    group.add_argument('--check-features', action='store_true',
                       help='Check feature availability at target arch.')

    parser.add_argument('--arch', metavar='VERSION',
                        help='Target architecture version (e.g. v9Ap4).')
    parser.add_argument('--category', metavar='CAT',
                        help='Filter templates or rules by category '
                             '(sve2, sme, pac, bti, mte, general).')
    parser.add_argument('--input', metavar='FILE',
                        help='Input assembly file (for --auto-pac-bti).')
    parser.add_argument('--output', choices=['text', 'json'], default='text',
                        help='Output format: text (default) or json.')
    parser.add_argument('feat_names', nargs='*', metavar='EXT',
                        help='Extension names for --check-features (e.g. SVE2 MTE).')

    args = parser.parse_args()

    # Dispatch
    if args.list_templates:
        return cmd_list_templates(args.category, args.output)

    if args.template:
        if not args.arch:
            print('ERROR: --template requires --arch.', file=sys.stderr)
            return 1
        return cmd_generate_template(args.template, args.arch, args.output)

    if args.auto_pac_bti:
        if not args.arch:
            print('ERROR: --auto-pac-bti requires --arch.', file=sys.stderr)
            return 1
        return cmd_auto_pac_bti(args.arch, args.input, args.output)

    if args.mte_helpers:
        if not args.arch:
            print('ERROR: --mte-helpers requires --arch.', file=sys.stderr)
            return 1
        return cmd_mte_helpers(args.arch, args.output)

    if args.list_rules:
        return cmd_list_rules(args.category, args.output)

    if args.check_features:
        if not args.arch:
            print('ERROR: --check-features requires --arch.', file=sys.stderr)
            return 1
        if not args.feat_names:
            print('ERROR: --check-features requires extension names '
                  '(e.g. SVE2 MTE PAC).', file=sys.stderr)
            return 1
        return cmd_check_features(args.arch, args.feat_names, args.output)

    # No command specified
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
