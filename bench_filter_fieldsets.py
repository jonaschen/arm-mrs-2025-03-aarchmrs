import timeit

setup = """
fieldsets = [{'gic_versions': [f'v{i}' for i in range(1, 101)]}] * 1000
version = 'v1'

def filter_original(fieldsets, version):
    v = version.lower()
    return [fs for fs in fieldsets if v in [gv.lower() for gv in fs.get('gic_versions', [])]]

def filter_any_gen(fieldsets, version):
    v = version.lower()
    return [fs for fs in fieldsets if any(v == gv.lower() for gv in fs.get('gic_versions', []))]
"""

code_original = "filter_original(fieldsets, version)"
code_any_gen = "filter_any_gen(fieldsets, version)"

print("Original:", timeit.timeit(code_original, setup=setup, number=1000))
print("any+gen:", timeit.timeit(code_any_gen, setup=setup, number=1000))
