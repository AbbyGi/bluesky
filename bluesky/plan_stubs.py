import itertools
import uuid

try:
    # cytools is a drop-in replacement for toolz, implemented in Cython
    from cytools import partition
except ImportError:
    from toolz import partition


from .utils import (separate_devices, all_safe_rewind, Msg,
                    short_uid as _short_uid)


def create(name='primary'):
    """
    Bundle future readings into a new Event document.

    Parameters
    ----------
    name : string, optional
        name given to event stream, used to convenient identification
        default is 'primary'

    Yields
    ------
    msg : Msg
        Msg('create', name=name)

    See Also
    --------
    :func:`bluesky.plans.save`
    """
    return (yield Msg('create', name=name))


def save():
    """
    Close a bundle of readings and emit a completed Event document.

    Yields
    -------
    msg : Msg
        Msg('save')

    See Also
    --------
    :func:`bluesky.plans.create`
    """
    return (yield Msg('save'))


def read(obj):
    """
    Take a reading and add it to the current bundle of readings.

    Parameters
    ----------
    obj : Device or Signal

    Yields
    ------
    msg : Msg
        Msg('read', obj)
    """
    return (yield Msg('read', obj))


def monitor(obj, *, name=None, **kwargs):
    """
    Asynchronously monitor for new values and emit Event documents.

    Parameters
    ----------
    obj : Signal
    args :
        passed through to ``obj.subscribe()``
    name : string, optional
        name of event stream; default is None
    kwargs :
        passed through to ``obj.subscribe()``

    Yields
    ------
    msg : Msg
        ``Msg('monitor', obj, *args, **kwargs)``

    See Also
    --------
    :func:`bluesky.plans.unmonitor`
    """
    return (yield Msg('monitor', obj, name=name, **kwargs))


def unmonitor(obj):
    """
    Stop monitoring.

    Parameters
    ----------
    obj : Signal

    Yields
    ------
    msg : Msg
        Msg('unmonitor', obj)

    See Also
    --------
    :func:`bluesky.plans.monitor`
    """
    return (yield Msg('unmonitor', obj))


def null():
    """
    Yield a no-op Message. (Primarily for debugging and testing.)

    Yields
    ------
    msg : Msg
        Msg('null')
    """
    return (yield Msg('null'))


def abs_set(obj, *args, group=None, wait=False, **kwargs):
    """
    Set a value. Optionally, wait for it to complete before continuing.

    Parameters
    ----------
    obj : Device
    group : string (or any hashable object), optional
        identifier used by 'wait'
    wait : boolean, optional
        If True, wait for completion before processing any more messages.
        False by default.
    args :
        passed to obj.set()
    kwargs :
        passed to obj.set()

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.rel_set`
    :func:`bluesky.plans.wait`
    :func:`bluesky.plans.mv`
    """
    if wait and group is None:
        group = str(uuid.uuid4())
    ret = yield Msg('set', obj, *args, group=group, **kwargs)
    if wait:
        yield Msg('wait', None, group=group)
    return ret


def rel_set(obj, *args, group=None, wait=False, **kwargs):
    """
    Set a value relative to current value. Optionally, wait before continuing.

    Parameters
    ----------
    obj : Device
    group : string (or any hashable object), optional
        identifier used by 'wait'; None by default
    wait : boolean, optional
        If True, wait for completion before processing any more messages.
        False by default.
    args :
        passed to obj.set()
    kwargs :
        passed to obj.set()

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.abs_set`
    :func:`bluesky.plans.wait`
    """
    from .preprocessors import relative_set_wrapper
    return (yield from relative_set_wrapper(
        abs_set(obj, *args, group=group, wait=wait, **kwargs)))


def mv(*args):
    """
    Move one or more devices to a setpoint. Wait for all to complete.

    If more than one device is specifed, the movements are done in parallel.

    Parameters
    ----------
    args :
        device1, value1, device2, value2, ...

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.abs_set`
    :func:`bluesky.plans.mvr`
    """
    group = str(uuid.uuid4())
    status_objects = []
    for obj, val in partition(2, args):
        ret = yield Msg('set', obj, val, group=group)
        status_objects.append(ret)
    yield Msg('wait', None, group=group)
    return tuple(status_objects)


mov = mv  # synonym


def mvr(*args):
    """
    Move one or more devices to a relative setpoint. Wait for all to complete.

    If more than one device is specifed, the movements are done in parallel.

    Parameters
    ----------
    args :
        device1, value1, device2, value2, ...

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.rel_set`
    :func:`bluesky.plans.mv`
    """
    objs = []
    for obj, val in partition(2, args):
        objs.append(obj)

    from .preprocessors import relative_set_decorator

    @relative_set_decorator(objs)
    def inner_mvr():
        return (yield from mv(*args))

    return (yield from inner_mvr())


movr = mvr  # synonym


def stop(obj):
    """
    Stop a device.

    Parameters
    ----------
    obj : Device

    Yields
    ------
    msg : Msg
    """
    return (yield Msg('stop', obj))


def trigger(obj, *, group=None, wait=False):
    """
    Trigger and acquisition. Optionally, wait for it to complete.

    Parameters
    ----------
    obj : Device
    group : string (or any hashable object), optional
        identifier used by 'wait'; None by default
    wait : boolean, optional
        If True, wait for completion before processing any more messages.
        False by default.

    Yields
    ------
    msg : Msg
    """
    ret = yield Msg('trigger', obj, group=group)
    if wait:
        yield Msg('wait', None, group=group)
    return ret


def sleep(time):
    """
    Tell the RunEngine to sleep, while asynchronously doing other processing.

    This is not the same as ``import time; time.sleep()`` because it allows
    other actions, like interruptions, to be processed during the sleep.

    Parameters
    ----------
    time : float
        seconds

    Yields
    ------
    msg : Msg
        Msg('sleep', None, time)
    """
    return (yield Msg('sleep', None, time))


def wait(group=None):
    """
    Wait for all statuses in a group to report being finished.

    Parameters
    ----------
    group : string (or any hashable object), optional
        idenified given to `abs_set`, `rel_set`, `trigger`; None by default

    Yields
    ------
    msg : Msg
        Msg('wait', None, group=group)
    """
    return (yield Msg('wait', None, group=group))


_wait = wait  # for internal references to avoid collision with 'wait' kwarg


def checkpoint():
    """
    If interrupted, rewind to this point.

    Yields
    ------
    msg : Msg
        Msg('checkpoint')

    See Also
    --------
    :func:`bluesky.plans.clear_checkpoint`
    """
    return (yield Msg('checkpoint'))


def clear_checkpoint():
    """
    Designate that it is not safe to resume. If interrupted or paused, abort.

    Yields
    ------
    msg : Msg
        Msg('clear_checkpoint')

    See Also
    --------
    :func:`bluesky.plans.checkpoint`
    """
    return (yield Msg('clear_checkpoint'))


def pause():
    """
    Pause and wait for the user to resume.

    Yields
    ------
    msg : Msg
        Msg('pause')

    See Also
    --------
    :func:`bluesky.plans.deferred_pause`
    :func:`bluesky.plans.sleep`
    """
    return (yield Msg('pause', None, defer=False))


def deferred_pause():
    """
    Pause at the next checkpoint.

    Yields
    ------
    msg : Msg
        Msg('pause', defer=True)

    See Also
    --------
    :func:`bluesky.plans.pause`
    :func:`bluesky.plans.sleep`
    """
    return (yield Msg('pause', None, defer=True))


def input_plan(prompt=''):
    """
    Prompt the user for text input.

    Parameters
    ----------
    prompt : str
        prompt string, e.g., 'enter user name' or 'enter next position'

    Yields
    ------
    msg : Msg
        Msg('input', prompt=prompt)
    """
    return (yield Msg('input', prompt=prompt))


def kickoff(obj, *, group=None, wait=False, **kwargs):
    """
    Kickoff a fly-scanning device.

    Parameters
    ----------
    obj : fly-able
        Device with 'kickoff', 'complete', and 'collect' methods
    group : string (or any hashable object), optional
        identifier used by 'wait'
    wait : boolean, optional
        If True, wait for completion before processing any more messages.
        False by default.
    kwargs
        passed through to ``obj.kickoff()``

    Yields
    ------
    msg : Msg
        Msg('kickoff', obj)

    See Also
    --------
    :func:`bluesky.plans.complete`
    :func:`bluesky.plans.collect`
    :func:`bluesky.plans.wait`
    """
    ret = (yield Msg('kickoff', obj, group=group, **kwargs))
    if wait:
        yield from _wait(group=group)
    return ret


def complete(obj, *, group=None, wait=False, **kwargs):
    """
    Tell a flyer, 'stop collecting, whenver you are ready'.

    The flyer returns a status object. Some flyers respond to this
    command by stopping collection and returning a finished status
    object immedately. Other flyers finish their given course and
    finish whenever they finish, irrespective of when this command is
    issued.

    Parameters
    ----------
    obj : fly-able
        Device with 'kickoff', 'complete', and 'collect' methods
    group : string (or any hashable object), optional
        identifier used by 'wait'
    wait : boolean, optional
        If True, wait for completion before processing any more messages.
        False by default.
    kwargs
        passed through to ``obj.complete()``

    Yields
    ------
    msg : Msg
        a 'complete' Msg and maybe a 'wait' message

    See Also
    --------
    :func:`bluesky.plans.kickoff`
    :func:`bluesky.plans.collect`
    :func:`bluesky.plans.wait`
    """
    ret = yield Msg('complete', obj, group=group, **kwargs)
    if wait:
        yield from _wait(group=group)
    return ret


def collect(obj, *, stream=False):
    """
    Collect data cached by a fly-scanning device and emit documents.

    Parameters
    ----------
    obj : fly-able
        Device with 'kickoff', 'complete', and 'collect' methods
    stream : boolean
        If False (default), emit events documents in one bulk dump. If True,
        emit events one at time.

    Yields
    ------
    msg : Msg
        Msg('collect', obj)

    See Also
    --------
    :func:`bluesky.plans.kickoff`
    :func:`bluesky.plans.complete`
    :func:`bluesky.plans.wait`
    """
    return (yield Msg('collect', obj, stream=stream))


def configure(obj, *args, **kwargs):
    """
    Change Device configuration and emit an updated Event Descriptor document.

    Parameters
    ----------
    obj : Device
    args
        passed through to ``obj.configure()``
    kwargs
        passed through to ``obj.configure()``

    Yields
    ------
    msg : Msg
        ``Msg('configure', obj, *args, **kwargs)``
    """
    return (yield Msg('configure', obj, *args, **kwargs))


def stage(obj):
    """
    'Stage' a device (i.e., prepare it for use, 'arm' it).

    Parameters
    ----------
    obj : Device

    Yields
    ------
    msg : Msg
        Msg('stage', obj)

    See Also
    --------
    :func:`bluesky.plans.unstage`
    """
    return (yield Msg('stage', obj))


def unstage(obj):
    """
    'Unstage' a device (i.e., put it in standby, 'disarm' it).

    Parameters
    ----------
    obj : Device

    Yields
    ------
    msg : Msg
        Msg('unstage', obj)

    See Also
    --------
    :func:`bluesky.plans.stage`
    """
    return (yield Msg('unstage', obj))


def subscribe(name, func):
    """
    Subscribe the stream of emitted documents.

    Parameters
    ----------
    name : {'all', 'start', 'descriptor', 'event', 'stop'}
    func : callable
        Expected signature: ``f(name, doc)`` where ``name`` is one of the
        strings above ('all, 'start', ...) and ``doc`` is a dict

    Yields
    ------
    msg : Msg
        Msg('subscribe', None, func, name)

    See Also
    --------
    :func:`bluesky.plans.unsubscribe`
    """
    return (yield Msg('subscribe', None, func, name))


def unsubscribe(token):
    """
    Remove a subscription.

    Parameters
    ----------
    token : int
        token returned by processing a 'subscribe' message

    Yields
    ------
    msg : Msg
        Msg('unsubscribe', token=token)

    See Also
    --------
    :func:`bluesky.plans.subscribe`
    """
    return (yield Msg('unsubscribe', token=token))


def open_run(md=None):
    """
    Mark the beginning of a new 'run'. Emit a RunStart document.

    Parameters
    ----------
    md : dict, optional
        metadata

    Yields
    ------
    msg : Msg
        ``Msg('open_run', **md)``

    See Also
    --------
    :func:`bluesky.plans.close_run`
    """
    return (yield Msg('open_run', **(md or {})))


def close_run(exit_status=None, reason=None):
    """
    Mark the end of the current 'run'. Emit a RunStop document.

    Yields
    ------
    msg : Msg
        Msg('close_run')
    exit_status : {None, 'success', 'abort', 'fail'}
        The exit status to report in the Stop document
    reason : str, optional
        Long-form description of why the run ended

    See Also
    --------
    :func:`bluesky.plans.open_run`
    """
    return (yield Msg('close_run', exit_status=exit_status, reason=reason))


def wait_for(futures, **kwargs):
    """
    Low-level: wait for a list of ``asyncio.Future`` objects to set (complete).

    Parameters
    ----------
    futures : collection
        collection of asyncio.Future objects
    kwargs
        passed through to ``asyncio.wait()``

    Yields
    ------
    msg : Msg
        ``Msg('wait_for', None, futures, **kwargs)``

    See Also
    --------
    :func:`bluesky.plans.wait`
    """
    return (yield Msg('wait_for', None, futures, **kwargs))


def trigger_and_read(devices, name='primary'):
    """
    Trigger and read a list of detectors and bundle readings into one Event.

    Parameters
    ----------
    devices : iterable
        devices to trigger (if they have a trigger method) and then read
    name : string, optional
        event stream name, a convenient human-friendly identifier; default
        name is 'primary'

    Yields
    ------
    msg : Msg
        messages to 'trigger', 'wait' and 'read'
    """
    # If devices is empty, don't emit 'create'/'save' messages.
    if not devices:
        yield from null()
    devices = separate_devices(devices)  # remove redundant entries
    rewindable = all_safe_rewind(devices)  # if devices can be re-triggered

    def inner_trigger_and_read():
        grp = _short_uid('trigger')
        no_wait = True
        for obj in devices:
            if hasattr(obj, 'trigger'):
                no_wait = False
                yield from trigger(obj, group=grp)
        # Skip 'wait' if none of the devices implemented a trigger method.
        if not no_wait:
            yield from wait(group=grp)
        yield from create(name)
        ret = {}  # collect and return readings to give plan access to them
        for obj in devices:
            reading = (yield from read(obj))
            if reading is not None:
                ret.update(reading)
        yield from save()
        return ret
    from .preprocessors import rewindable_wrapper
    return (yield from rewindable_wrapper(inner_trigger_and_read(),
                                          rewindable))


def broadcast_msg(command, objs, *args, **kwargs):
    """
    Generate many copies of a mesasge, applying it to a list of devices.

    Parameters
    ----------
    command : string
    devices : iterable
    ``*args``
        args for message
    ``**kwargs``
        kwargs for message

    Yields
    ------
    msg : Msg
    """
    return_vals = []
    for o in objs:
        ret = yield Msg(command, o, *args, **kwargs)
        return_vals.append(ret)

    return return_vals


def repeater(n, gen_func, *args, **kwargs):
    """
    Generate n chained copies of the messages from gen_func

    Parameters
    ----------
    n : int or None
        total number of repetitions; if None, infinite
    gen_func : callable
        returns generator instance
    ``*args``
        args for gen_func
    ``**kwargs``
        kwargs for gen_func

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.caching_repeater`
    """
    it = range
    if n is None:
        n = 0
        it = itertools.count

    for j in it(n):
        yield from gen_func(*args, **kwargs)


def caching_repeater(n, plan):
    """
    Generate n chained copies of the messages in a plan.

    This is different from ``repeater`` above because it takes in a
    generator or iterator, not a function that returns one.

    Parameters
    ----------
    n : int or None
        total number of repetitions; if None, infinite
    plan : iterable

    Yields
    ------
    msg : Msg

    See Also
    --------
    :func:`bluesky.plans.repeater`
    """
    it = range
    if n is None:
        n = 0
        it = itertools.count

    lst_plan = list(plan)
    for j in it(n):
        yield from (m for m in lst_plan)


def one_1d_step(detectors, motor, step):
    """
    Inner loop of a 1D step scan

    This is the default function for ``per_step`` param in 1D plans.
    """
    def move():
        grp = _short_uid('set')
        yield Msg('checkpoint')
        yield Msg('set', motor, step, group=grp)
        yield Msg('wait', None, group=grp)

    yield from move()
    return (yield from trigger_and_read(list(detectors) + [motor]))


def one_nd_step(detectors, step, pos_cache):
    """
    Inner loop of an N-dimensional step scan

    This is the default function for ``per_step`` param`` in ND plans.

    Parameters
    ----------
    detectors : iterable
        devices to read
    step : dict
        mapping motors to positions in this step
    pos_cache : dict
        mapping motors to their last-set positions
    """
    def move():
        yield Msg('checkpoint')
        grp = _short_uid('set')
        for motor, pos in step.items():
            if pos == pos_cache[motor]:
                # This step does not move this motor.
                continue
            yield Msg('set', motor, pos, group=grp)
            pos_cache[motor] = pos
        yield Msg('wait', None, group=grp)

    motors = step.keys()
    yield from move()
    yield from trigger_and_read(list(detectors) + list(motors))
