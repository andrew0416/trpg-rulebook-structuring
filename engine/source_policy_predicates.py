"""Typed authored conditions over explicit inputs; no eval or implicit coercion."""
import root_resolution as R


def _negate(predicate):
    truth={R.Truth.TRUE:R.Truth.FALSE,R.Truth.FALSE:R.Truth.TRUE,R.Truth.UNKNOWN:R.Truth.UNKNOWN}[predicate.truth]
    return R.Predicate(truth,predicate.obligation,predicate.reads)


def validate(expression, specs):
    def operand(value):
        if type(value) in (bool,int,str):return {bool:'boolean',int:'integer',str:'string'}[type(value)]
        if type(value) is dict and set(value)=={'$input'} and type(value['$input']) is str and value['$input'] in specs:
            return specs[value['$input']]['type']
        raise ValueError('typed literal or declared input operand required')
    def visit(node):
        if type(node) is bool:return
        if type(node) is not dict:raise ValueError('typed condition required')
        if set(node)=={'$input'}:
            if operand(node)!='boolean':raise ValueError('boolean condition input required')
        elif set(node) in ({'all'},{'any'}):
            children=next(iter(node.values()))
            if type(children) is not list or not children:raise ValueError('nonempty condition group required')
            for child in children:visit(child)
        elif set(node)=={'not'}:visit(node['not'])
        elif set(node)=={'op','left','right'}:
            if node['op'] not in ('eq','ne','lt','le','gt','ge'):raise ValueError('unsupported comparison')
            left,right=operand(node['left']),operand(node['right'])
            if left!=right or (node['op'] not in ('eq','ne') and left!='integer'):
                raise ValueError('comparison operands must have matching exact types; ordering requires integers')
        else:raise ValueError('unknown condition form')
    visit(expression)


def evaluate(expression, specs, values):
    validate(expression,specs)
    def operand(value):
        if type(value) is dict:
            key=value['$input']
            return values.get(key),((key,),),key if key not in values else ''
        return value,(),''
    def visit(node):
        if type(node) is bool:return R.TRUE if node else R.FALSE
        if '$input' in node:
            value,reads,missing=operand(node)
            return R.Predicate(R.Truth.UNKNOWN,'input:'+missing,reads) if missing else R.Predicate(R.Truth.TRUE if value else R.Truth.FALSE,reads=reads)
        if 'not' in node:return _negate(visit(node['not']))
        if 'all' in node:return R.conjunction(*(visit(child) for child in node['all']))
        if 'any' in node:return _negate(R.conjunction(*(_negate(visit(child)) for child in node['any'])))
        left,lr,lm=operand(node['left']);right,rr,rm=operand(node['right']);reads=lr+rr
        if lm or rm:return R.Predicate(R.Truth.UNKNOWN,';'.join('input:'+key for key in sorted({lm,rm}- {''})),reads)
        op=node['op']
        result={'eq':lambda:left==right,'ne':lambda:left!=right,'lt':lambda:left<right,
                'le':lambda:left<=right,'gt':lambda:left>right,'ge':lambda:left>=right}[op]()
        return R.Predicate(R.Truth.TRUE if result else R.Truth.FALSE,reads=reads)
    return visit(expression)
