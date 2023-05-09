{% if product == 'xpand' %}
dbset db xpand
{% else %}
dbset db {{prefix}}
{% endif %}

{% if bench == 'tpch' %}
dbset bm TPC-H
{% else %}
dbset bm TPC-C
{% endif %}

diset connection {{prefix}}_host {{host}}
diset connection {{prefix}}_port {{port}}
{% if prefix == 'pg' %}
diset {{bench}} {{prefix}}_superuser {{user}}
diset {{bench}} {{prefix}}_superuserpass {{password}}
diset {{bench}} {{prefix}}_defaultdbase {{database}}
{% endif %}
diset {{bench}} {{prefix}}_user {{user}}
diset {{bench}} {{prefix}}_pass {{password}}
diset {{bench}} {{prefix}}_dbase {{database}}
diset {{bench}} {{prefix}}_count_ware {{warehouses}}
diset {{bench}} {{prefix}}_raiseerror {{raise_error}}
diset {{bench}} {{prefix}}_partition {{partition}}
diset {{bench}} {{prefix}}_prepared {{prepared}}
{% if phase == 'load' %}
diset {{bench}} {{prefix}}_num_vu {{num_vu_load}}
print dict
buildschema
{% else %}
diset {{bench}} {{prefix}}_driver timed
diset {{bench}} {{prefix}}_rampup {{warmup_m}}
diset {{bench}} {{prefix}}_duration {{time_m}}
diset {{bench}} {{prefix}}_allwarehouse {{allwarehouse}}
diset {{bench}} {{prefix}}_timeprofile True
diset {{bench}} {{prefix}}_keyandthink {{keyandthink}}
print dict
tcset logtotemp {{logtotemp}}
tcset timestamps {{timestamps}}
tcset refreshrate {{refreshrate}}
print tcconf
loadscript
vuset vu {{virtusers}}
vuset delay {{delay}}
print vuconf
vucreate
tcstart
vurun
vudestroy
{% endif %}
