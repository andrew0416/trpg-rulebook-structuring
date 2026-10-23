"""Ruleset-independent physical limit arithmetic; no PTK values or actions."""
import math
from fractions import Fraction
import composition_derive as COMPOSITION
def number(value,name,minimum=None):
    if type(value) not in (int,float) or not math.isfinite(value) or (minimum is not None and value<minimum):
        raise ValueError('invalid '+name)
    return value

def add_sources(base,contributions):
    """Adapt finite native measurements to exact sourced addition, without rounding."""
    def exact(value):
        number(value,'native composition value')
        if type(value) is int:return value
        ratio=Fraction(str(value))
        return {'numerator':ratio.numerator,'denominator':ratio.denominator}
    rows=[dict(row,value=exact(row['value'])) for row in contributions]
    result=COMPOSITION.derive(exact(base),rows,
        [{'law':'add','contributors':[row['id'] for row in rows]}] if rows else [],rounding='exact')
    value=result['value']
    if type(value) is dict:value=value['numerator']/value['denominator']
    if type(base) is float or any(type(row['value']) is float for row in contributions):value=float(value)
    result['value']=value
    return result
def shifted_stage(base,delta,minimum,maximum):
    return max(minimum,min(maximum,base+delta))
def classify_load(weight,heavy,staggering,boundary_band=None):
    number(weight,'carried weight',minimum=0)
    if not isinstance(heavy,(list,tuple)) or len(heavy)!=2:
        raise ValueError('two ordered heavy-load boundaries required')
    lo,hi=(number(v,'heavy-load boundary',minimum=0) for v in heavy)
    number(staggering,'staggering-load limit',minimum=0)
    if not lo<hi<=staggering:
        raise ValueError('ordered heavy and staggering load limits required')
    if weight==lo:
        if boundary_band is None:return 'boundary'
        if boundary_band not in ('normal','heavy'):raise ValueError('invalid lower-boundary ruling')
        return boundary_band
    if weight==hi:
        if boundary_band is None:return 'boundary'
        if boundary_band not in ('heavy','staggering'):raise ValueError('invalid upper-boundary ruling')
        return boundary_band
    if boundary_band is not None:raise ValueError('boundary ruling cannot override an ordinary interval')
    return 'normal' if weight<lo else 'heavy' if weight<hi else 'staggering' if weight<=staggering else 'too_heavy'
