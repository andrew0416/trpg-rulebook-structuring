"""Publish connected test outputs only after their complete unittest case succeeds."""


def case_is_unverified(test, result):
    if result is None:
        return False
    bad = [case for case, _ in result.failures + result.errors + result.skipped + result.expectedFailures]
    bad += result.unexpectedSuccesses
    return any(case is test or getattr(case, 'test_case', None) is test for case in bad)


def bind_case_lifecycle(test, poison):
    """Observe this exact instance, without replacing its ID, class or result."""
    if hasattr(test, '_chain_case_lifecycle'):
        raise ValueError('test case already has a chained lifecycle')
    state = {'running': False, 'pending': None, 'poisoned': False}
    test._chain_case_lifecycle = state
    original_run, original_debug = test.run, test.debug

    def poison_once(reason):
        if state['poisoned']:
            return
        state['poisoned'] = True
        try:
            poison(reason)
        except BaseException as error:
            state['poison_error'] = error
            raise

    def preserve_exception(reason):
        try:
            poison_once(reason)
        except BaseException:
            pass # Retained in state; a secondary callback cannot hide the original exception.

    def run(result=None):
        state.update(running=True, pending=None)
        try:
            result = original_run(result)
            rejected = result is None or case_is_unverified(test, result)
            if rejected or state['pending'] is None or state['poisoned']:
                poison_once(test.id() + ': whole TestCase not verified')
            else:
                state['pending']()
            return result
        except BaseException as error:
            preserve_exception(test.id() + ': ' + type(error).__name__)
            raise
        finally:
            state.update(running=False, pending=None)

    def debug():
        state.update(running=True, pending=None)
        try:
            value = original_debug()
            if state['pending'] is None or state['poisoned']:
                poison_once(test.id() + ': debug has no completed stage')
            else:
                state['pending']()
            return value
        except BaseException:
            preserve_exception(test.id() + ': debug failed')
            raise
        finally:
            state.update(running=False, pending=None)

    state['poison'] = poison_once
    test.run, test.debug = run, debug


def defer_case_commit(test, commit):
    """A direct body call has no whole-case boundary and cannot publish."""
    state = test._chain_case_lifecycle
    if not state['running']:
        state['poison'](test.id() + ': body called outside TestCase.run')
        return
    if state['pending'] is not None:
        raise AssertionError('chained case registered multiple commits')
    state['pending'] = commit
