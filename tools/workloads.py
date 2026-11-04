"""Validated digital RTL simulation settings for the E6 EDA demo."""
WORKLOADS = {
    'rtl': {'name':'Digital RTL simulation','job':'eda-e6-rtl-workers','cycles':100000000,
            'warmup':1000000,'unit':'clock cycles','command':['/work/obj/Vtb','+seed={seed}','+cycles={cycles}']},
}
