"""
This module includes function decorators and onlyif subclasses to simplify
Jython rule definitions.

If using a build of openHAB **prior** to S1566 or 2.5M2, see
:ref:`Guides/Triggers:System Started` for a ``System started`` workaround. For
everyone, see :ref:`Guides/Triggers:System Shuts Down` for a method of
executing a function when a script is unloaded, simulating a
``System shuts down`` trigger. Along with the ``onlyif`` decorator, this module
includes the following Trigger subclasses (see :ref:`Guides/Rules:Extensions`
for more details):
"""

try:
    # pylint: disable=unused-import
    import typing
    if typing.TYPE_CHECKING:
        from core.jsr223.scope import (
            itemRegistry as t_itemRegistry
        )
    # pylint: enable=unused-import
except:
    pass

from core.jsr223.scope import scriptExtension
scriptExtension.importPreset("RuleSupport")
from core.jsr223.scope import ConditionBuilder, Configuration, Condition
from core.utils import validate_uid
from core.log import getLogger
import re

from os import path

from org.openhab.core.thing import ChannelUID, ThingUID, ThingStatus
from org.openhab.core.thing.type import ChannelKind
from org.openhab.core.types import TypeParser

# Lazy load itemRegistry
itemRegistry = None
def getItem(itemName):
    global itemRegistry
    if itemRegistry is None:
        itemRegistry = scriptExtension.get("itemRegistry") # type: t_itemRegistry
    return itemRegistry.getItem(itemName)

log = getLogger(u"core.onlyif")

class ItemStateCondition(Condition):
    def __init__(self, item_name, operator, state, condition_name=None):
        condition_name = validate_uid(condition_name)
        configuration = { 
            "itemName": item_name,
            "operator": operator,
            "state": state
        }
        if any(value is None for value in configuration.values()):
            raise ValueError(u"Paramater invalid in call to ItemStateConditon")

        self.condition = ConditionBuilder.create().withId(condition_name).withTypeUID("core.ItemStateCondition").withConfiguration(Configuration(configuration)).build()

    firstWord = "item"
    @classmethod
    def parse(cls, target):
        # @onlyif("Item Test_Switch_2 equals ON")
        match = re.match(r"^Item\s+(?P<itemName>\w+)\s+((?P<eq>=|==|eq|equals|is)|(?P<neq>!=|not\s+equals|is\s+not)|(?P<lt><|lt|is\s+less\s+than)|(?P<lte><=|lte|is\s+less\s+than\s+or\s+equal)|(?P<gt>>|gt|is\s+greater\s+than)|(?P<gte>>=|gte|is\s+greater\s+than\s+or\s+equal))\s+(?P<state>'[^']+'|\S+)*$", target, re.IGNORECASE)
        if match is not None:
            item = getItem(match.group('itemName'))
            if item is None:
                raise ValueError(u"Invalid item name: {}".format(match.group('itemName')))

            operators = [("eq", "="), ("neq", "!="), ("lt", "<"), ("lte", "<="), ("gt", ">"), ("gte", ">=")]
            condition = next((op[1] for op in operators if match.group(op[0]) is not None), None)

            return cls(match.group('itemName'), condition, match.group('state'))

class EphemerisCondition(Condition):
    def __init__(self, dayset, offset=0, condition_name=None):
        condition_name = validate_uid(condition_name)

        configuration = { 
            "offset": offset
        }

        typeuid = {
            "holiday":      "ephemeris.HolidayCondition",
            "notholiday":   "ephemeris.NotHolidayCondition",
            "weekend":      "ephemeris.WeekendCondition",
            "weekday":      "ephemeris.WeekdayCondition"
        }.get(dayset)

        if typeuid is None:
            typeuid = "epemeris.DaysetCondition"
            configuration['dayset'] = dayset

        self.condition = ConditionBuilder.create().withId(condition_name).withTypeUID(typeuid).withConfiguration(Configuration(configuration)).build()

    firstWord = [ "today", "tomorrow", "yesterday", "it's" ]
    @classmethod
    def parse(cls, target):
        # @onlyif("Today is a holiday")
        # @onlyif("It's not a holiday")
        # @onlyif("tomorrow is not a holiday")
        # @onlyif("today plus 1 is weekend")
        # @onlyif("today minus 1 is weekday")
        # @onlyif("today plus 3 is a weekend")
        # @onlyif("today offset -3 is a weekend")
        # @onylyf("today minus 3 is not a holiday")
        # @onlyif("yesterday was in dayset")
        match = re.match(r"""^((?P<today>Today\s+is|it'*s)|(?P<plus1>Tomorrow\s+is|Today\s+plus\s+1)|(?P<minus1>Yesterday\s+was|Today\s+minus\s+1)|(Today\s+(?P<plusminus>plus|minus|offset)\s+(?P<offset>-?\d+)\s+is))\s+  # what day
                         (?P<not>not\s+)?(in\s+)?(a\s+)?                        # predicate
                         (?P<daytype>holiday|weekday|weekend|\S+)$""",          # daytype
                         target, re.IGNORECASE | re.X)
        if match is not None:
            daytype = match.group('daytype')
            if daytype is None:
                raise ValueError(u"Invalid ephemeris type: {}".format(match.group('daytype')))

            if match.group('today') is not None:
                offset = 0
            elif match.group('plus1') is not None:
                offset = 1
            elif match.group('minus1') is not None:
                offset = -1
            elif match.group('offset') is not None:
                offset = match.group('offset')
            else:
                raise ValueError(u"Offset is not specified")
            
            if match.group('not') is not None:
                if match.group('daytype') == "holiday":
                    daytype = "notholiday"
                elif match.group('daytype') == "weekday":
                    daytype = "weekend"
                elif match.group('daytype') == "weekend":
                    daytype = "weekday"
                else:
                    raise ValueError(u"Unable to negate custom daytype: {}", match.group('daytype'))
            else:
                daytype = match.group('daytype')

            return cls(daytype, offset)

class TimeOfDayCondition(Condition):
    def __init__(self, startTime, endTime, condition_name=None):
        condition_name = validate_uid(condition_name)
        configuration = { 
            "startTime": startTime,
            "endTime": endTime
        }
        if any(value is None for value in configuration.values()):
            raise ValueError(u"Paramater invalid in call to TimeOfDateCondition")

        self.condition = ConditionBuilder.create().withId(condition_name).withTypeUID("core.TimeOfDayCondition").withConfiguration(Configuration(configuration)).build()

    firstWord = "time"
    @classmethod
    def parse(cls, target):
        # @onlyif("Time 9:00 to 14:00")
        timeOfDayRegEx = r"(([01]?\d|2[0-3]):[0-5]\d)|((0?[1-9]|1[0-2]):[0-5]\d(:[0-5]\d)?\s?(AM|PM))"
        reFull = r"^Time\s+(?P<startTime>" + timeOfDayRegEx + r")(?:\s*-\s*|\s+to\s+)(?<endTime>" + timeOfDayRegEx + r")$"
        match = re.match(r"^Time\s+(?P<startTime>" + timeOfDayRegEx + r")(?:\s*-\s*|\s+to\s+)(?P<endTime>" + timeOfDayRegEx + r")$", target, re.IGNORECASE)
        if match is not None:
            return cls(match.group('startTime'), match.group('endTime'))

def onlyif(target):
    """
    This function decorator creates a ``condition`` attribute in the decorated
    function, which is used by the ``rule`` decorator when creating the rule.
    The ``onlyif`` decorator simplifies the use of many of the conditions in this
    module and allows for them to be used with natural language.
    """

    conditionClasses = [ ItemStateCondition, EphemerisCondition, TimeOfDayCondition ]

    def parse(target):
        target = target.strip()
        if len(target) <= 0:
            raise ValueError(u"expression is length 0")

        firstWord = target.split()[0]

        for conditionClass in conditionClasses:
            # check first word to eliminate unecessary regex compiles
            if firstWord.lower() in conditionClass.firstWord:
                condition = conditionClass.parse(target)
                if condition is not None:
                    return condition

        raise ValueError(u"Could not parse {} condition: {}".format(firstWord, target))

    try:
        def onlyifFunction(function):
            condition = parse(target)

            if condition == None:
                raise ValueError(u"Invalid condition: {}".format(target))

            if not hasattr(function, 'conditions'):
                function.conditions = []

            function.conditions.append(condition.condition)

            return function

        return onlyifFunction

    except ValueError as ex:
        log.warn(ex)

        def bad_condition(function):
            if not hasattr(function, 'conditions'):
                function.conditions = []
            function.conditions.append(None)
            return function

        # If there was a problem with a condition configuration, then add None
        # to the conditions attribute of the callback function, so that
        # core.rules.rule can identify that there was a problem and not start
        # the rule
        return bad_condition

    except:
        import traceback
        log.warn(traceback.format_exc())