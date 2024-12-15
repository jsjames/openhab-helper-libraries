"""
This module includes function decorators and Trigger subclasses to simplify
Jython rule definitions.

If using a build of openHAB **prior** to S1566 or 2.5M2, see
:ref:`Guides/Triggers:System Started` for a ``System started`` workaround. For
everyone, see :ref:`Guides/Triggers:System Shuts Down` for a method of
executing a function when a script is unloaded, simulating a
``System shuts down`` trigger. Along with the ``when`` decorator, this module
includes the following Trigger subclasses (see :ref:`Guides/Rules:Extensions`
for more details):

* **CronTrigger** - fires based on cron expression
* **DateTimeTrigger** - fires based on an item's Date Time
* **ItemStateChangeTrigger** - fires when the specified Item's State changes
* **ItemStateUpdateTrigger** - fires when the specified Item's State is updated
* **ItemCommandTrigger** - fires when the specified Item receives a Command
* **GenericEventTrigger** - fires when the specified Event occurs
* **ItemEventTrigger** - fires when an Item reports an Event (based on ``GenericEventTrigger``)
* **ThingEventTrigger** - fires when a Thing reports an Event (based on ``GenericEventTrigger``)
* **ThingStatusChangeTrigger** - fires when the specified Thing's status changes **(requires S1636, 2.5M2 or newer)**
* **ThingStatusUpdateTrigger** - fires when the specified Thing's status is updated **(requires S1636, 2.5M2 or newer)**
* **ChannelEventTrigger** - fires when a Channel reports an Event
* **StartupTrigger** - fires when the rule is activated **(implemented in Jython and requires S1566, 2.5M2 or newer)**
* **DirectoryEventTrigger** - fires when a directory reports an Event **(implemented in Jython and requires S1566, 2.5M2 or newer)**
"""
try:
    # pylint: disable=unused-import
    import typing
    if typing.TYPE_CHECKING:
        from core.jsr223.scope import (
            itemRegistry as t_itemRegistry,
            things as t_things
        )
        from java.nio.file import WatchEvent
    # pylint: enable=unused-import
except:
    pass

from core.jsr223.scope import scriptExtension
scriptExtension.importPreset("RuleSupport")
from core.jsr223.scope import TriggerBuilder, Configuration, Trigger
from core.utils import validate_uid
from core.log import getLogger
import re

from os import path

try:
    from org.openhab.core.thing import ChannelUID, ThingUID, ThingStatus
    from org.openhab.core.thing.type import ChannelKind
except:
    from org.eclipse.smarthome.core.thing import ChannelUID, ThingUID, ThingStatus
    from org.eclipse.smarthome.core.thing.type import ChannelKind

try:
    from org.eclipse.smarthome.core.types import TypeParser
except:
        from org.openhab.core.types import TypeParser

from java.nio.file import StandardWatchEventKinds
ENTRY_CREATE = StandardWatchEventKinds.ENTRY_CREATE  # type: WatchEvent.Kind
ENTRY_DELETE = StandardWatchEventKinds.ENTRY_DELETE  # type: WatchEvent.Kind
ENTRY_MODIFY = StandardWatchEventKinds.ENTRY_MODIFY  # type: WatchEvent.Kind

try:
    from org.quartz.CronExpression import isValidExpression
except:
    # Quartz is removed in OH3, this needs to either impliment or match
    # functionality in `org.openhab.core.internal.scheduler.CronAdjuster`
    def isValidExpression(expr):
        expr = expr.strip()
        if expr.startswith("@"):
            return re.match(r"@(annually|yearly|monthly|weekly|daily|hourly|reboot)", expr) is not None

        parts = expr.split()
        if 6 <= len(parts) <= 7:
            for i in range(len(parts)):
                if not re.match(
                    r"\?|(\*|\d+)(\/\d+)?|(\d+|\w{3})(\/|-)(\d+|\w{3})|((\d+|\w{3}),)*(\d+|\w{3})", parts[i]
                ):
                    return False
            return True
            return False

# Lazy load itemRegistry
itemRegistry = None
def getItem(itemName):
    global itemRegistry
    if itemRegistry is None:
        itemRegistry = scriptExtension.get("itemRegistry") # type: t_itemRegistry
    return itemRegistry.getItem(itemName)

# Lazy load things
things = None
def getChannel(channelUID):
    global things
    if things is None:
        things = scriptExtension.get("things") # type: t_things
    return things.getChannel(ChannelUID(channelUID))

def getThing(thingUID):
    global things
    if things is None:
        things = scriptExtension.get("things") #type t_things
    return things.get(ThingUID(thingUID))

LOG = getLogger(u"core.triggers")

class StartupTrigger(Trigger):
    def __init__(self, startLevel=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        if startLevel is None:
            startLevel = 40
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.SystemStartlevelTrigger").withConfiguration(Configuration({
            "startlevel": startLevel
        })).build()

    firstWord = "system"
    @classmethod
    def parse(cls, target):
        # @when("System started")# requires S1566, 2.5M2 or newer ('System shuts down' has not been implemented)
        # @when("System reached start level 50")
        match = re.match(r"^System\s+(?:started|reached\s+start\s+level\s+(?P<startLevel>\d+))$", target, re.IGNORECASE)
        if match is not None:
            return cls(match.group('startLevel'))

class CronTrigger(Trigger):
    def __init__(self, cron_expression, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {'cronExpression': cron_expression}
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("timer.GenericCronTrigger").withConfiguration(Configuration(configuration)).build()
            
    firstWord = "time"
    @classmethod
    def parse(cls, target):
        # @when("Time cron 55 55 5 * * ?")
        # @when("Time is midnight")
        # @when("Time is noon")
        match = re.match(r"^Time\s+(?:cron\s+(?P<cronExpression>.*)|is\s+(?P<namedInstant>midnight|noon))$", target, re.IGNORECASE)
        if match is not None:
            if match.group('namedInstant') is None:
                cronExpression = match.group('cronExpression')
            elif match.group(2) == "midnight":
                cronExpression = "0 0 0 * * ?"
            else:   # noon
                cronExpression = "0 0 12 * * ?"
        else:
            cronExpression = target

        if isValidExpression(cronExpression):
            return cls(cronExpression)

        return None

class DateTimeTrigger(Trigger):
    def __init__(self, itemName, timeOnly=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = { 'itemName': itemName }
        if timeOnly is not None:
            configuration["timeOnly"] = timeOnly
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("timer.DateTimeTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = "time"
    @classmethod
    def parse(cls, target):
        # @when("Time is itemName")
        match = re.match(r"^Time\s+is\s+(?P<itemName>\S*)(?:\s+\[(?P<timeOnly>timeOnly)\])*$", target, re.IGNORECASE)
        if match is not None:
            item = getItem(match.group('itemName'))
            if item is None:
                raise ValueError(u"Invalid item name: {}".format(match.group('itemName')))
            return cls(match.group('itemName'), match.group('timeOnly') == "timeOnly")

class ItemStateUpdateTrigger(Trigger):
    def __init__(self, item_name, state=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {"itemName": item_name}
        if state is not None:
            configuration["state"] = state
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ItemStateUpdateTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = [ "item", "member", "descendent" ]
    @classmethod
    def parse(cls, target):
        # @when("Item Test_Switch_2 received update ON")
        # @when("Member of gIrrigationEvents received update")
        # TODO - add support for TimeOnly flag
        match = re.match(r"^(?:(?P<subItems>Member|Descendent)\s+of|Item)\s+(?P<itemName>\w+)\s+received\s+update(?:\s+(?P<state>'[^']+'|\S+))*$", target, re.IGNORECASE)
        if match is not None:
            item = getItem(match.group('itemName'))
            if item is None:
                raise ValueError(u"Invalid item name: {}".format(match.group('itemName')))

            if match.group('subItems') is None:
                return cls(match.group('itemName'), match.group('state'))

            groupMembers = item.getMembers() if match.group('subItems') == "Member" else item.getAllMembers()
            return list(map(lambda item: cls(item.name, match.group('state')), groupMembers)) 

class ItemStateChangeTrigger(Trigger):
    def __init__(self, item_name, previous_state=None, state=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {"itemName": item_name}
        if state is not None:
            configuration["state"] = state
        if previous_state is not None:
            configuration["previousState"] = previous_state
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ItemStateChangeTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = [ "item", "member", "descendent" ]
    @classmethod
    def parse(cls, target):
        # @when("Item Test_String_1 changed from 'old test string' to 'new test string'")
        # @when("Item gMotion_Sensors changed")
        # @when("Member of gMotion_Sensors changed from ON to OFF")
        # @when("Descendent of gContact_Sensors changed from OPEN to CLOSED")
        match = re.match(r"^(?:(?P<subItems>Member|Descendent)\s+of|Item)\s+(?P<itemName>\w+)\s+changed(?:\s+from\s+(?P<previousState>'[^']+'|\S+))*(?:\s+to\s+(?P<state>'[^']+'|\S+))*$", target, re.IGNORECASE)
        if match is not None:
            item = getItem(match.group('itemName'))
            if item is None:
                raise ValueError(u"Invalid item name: {}".format(match.group('itemName')))

            if match.group('subItems') is None:
                return cls(match.group('itemName'), match.group('previousState'), match.group('state'))

            groupMembers = item.getMembers() if match.group('subItems') == "Member" else item.getAllMembers()
            return list(map(lambda item: cls(item.name, match.group('previousState'), match.group('state')), groupMembers)) 

class ItemCommandTrigger(Trigger):
    def __init__(self, item_name, command=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)

        configuration = {"itemName": item_name}
        if command is not None:
            configuration["command"] = command
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ItemCommandTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = [ "item", "member", "descendent" ]
    @classmethod
    def parse(cls, target):
        # @when("Item Test_Switch_1 received command OFF")
        match = re.match(r"^(?:(?P<subItems>Member|Descendent)\s+of|Item)\s+(?P<itemName>\w+)\s+received\s+command(?:\s+(?P<command>\w+))*$", target, re.IGNORECASE)
        if match is not None:
            item = getItem(match.group('itemName'))
            if item is None:
                raise ValueError(u"Invalid item name: {}".format(match.group('itemName')))

            if match.group('subItems') is None:
                return cls(match.group('itemName'), match.group('command'))

            groupMembers = item.getMembers() if match.group('subItems') == "Member" else item.getAllMembers()
            return list(map(lambda item: cls(item.name, match.group('command')), groupMembers)) 

class ThingStatusUpdateTrigger(Trigger):
    def __init__(self, thing_uid, status=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {"thingUID": thing_uid}
        if status is not None:
            configuration["status"] = status
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ThingStatusUpdateTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = "thing"
    @classmethod
    def parse(cls, target):
        # @when("Thing kodi:kodi:familyroom received update ONLINE")# requires S1636, 2.5M2 or newer
        match = re.match(r"^Thing\s+(?P<thingUID>\S+)\s+received\s+update(?:\s+(?P<status>\w+))*$", target, re.IGNORECASE)
        if match is not None:
            if getThing(match.group('thingUID')) is None:
                raise ValueError(u"Invalid thing UID: {}".format(match.group('thingUID')))
            return cls(match.group('thingUID'), match.group('status'))

class ThingStatusChangeTrigger(Trigger):
    def __init__(self, thing_uid, previous_status=None, status=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {"thingUID": thing_uid}
        if previous_status is not None:
            configuration["previousStatus"] = previous_status
        if status is not None:
            configuration["status"] = status
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ThingStatusChangeTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = "thing"
    @classmethod
    def parse(cls, target):
        match = re.match(r"^Thing\s+(?P<thingUID>\S+)\s+changed(?:\s+from\s+(?P<previousState>\w+))*(?:\s+to\s+(?P<state>\w+))*$", target, re.IGNORECASE)
        if match is not None:
            if getThing(match.group('thingUID')) is None:
                raise ValueError(u"Invalid thing UID: {}".format(match.group('thingUID')))
            return cls(match.group('thingUID'), match.group('previousState'), match.group('state'))

class ChannelEventTrigger(Trigger):
    def __init__(self, channel_uid, event=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {"channelUID": channel_uid}
        if event is not None:
            configuration["event"] = event
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.ChannelEventTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = "channel"
    @classmethod
    def parse(cls, target):
        # @when("Thing kodi:kodi:familyroom changed")
        # @when("Thing kodi:kodi:familyroom changed from ONLINE to OFFLINE")# requires S1636, 2.5M2 or newer
        match = re.match(r'^Channel\s+\"*(?P<channelUID>\S+)\"*\s+triggered(?:\s+(?P<event>\w+))*$', target, re.IGNORECASE)
        if match is not None:
            if getChannel(match.group('channelUID')) is None:
                raise ValueError(u"Invalid channel UID: {}".format(match.group('channelUID'))) 
            return cls(match.group('channelUID'), match.group('event'))

class GenericEventTrigger(Trigger):
    def __init__(self, event_source, event_types, event_topic="smarthome/*", trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.GenericEventTrigger").withConfiguration(Configuration({
            "eventTopic": event_topic,
            "eventSource": event_source,
            "eventTypes": event_types
        })).build()

class ItemEventTrigger(Trigger):
    def __init__(self, event_types, item_name=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.GenericEventTrigger").withConfiguration(Configuration({
            "eventTopic": "smarthome/items/*",
            "eventSource": "smarthome/items/{}".format("{}/".format(item_name) if item_name else ""),
            "eventTypes": event_types
        })).build()

    firstWord = "item"
    @classmethod
    def parse(cls, target):
        # @when("Item added")
        # @when("Item removed")
        # @when("Item updated")
        match = re.match(r"^Item\s+(?P<action>added|removed|updated)$", target, re.IGNORECASE)
        if match is not None:
            event_names = {
                "added": "ItemAddedEvent",
                "removed": "ItemRemovedEvent",
                "updated": "ItemUpdatedEvent"
            }
            return cls(event_names.get(match.group('action')))

class ThingEventTrigger(Trigger):
    def __init__(self, event_types, thing_uid=None, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("core.GenericEventTrigger").withConfiguration(Configuration({
            "eventTopic": "smarthome/things/*",
            "eventSource": "smarthome/things/{}".format("{}/".format(thing_uid) if thing_uid else ""),
            "eventTypes": event_types
        })).build()

    firstWord = "thing"
    @classmethod
    def parse(cls, target):
        # @when("Thing added")
        # @when("Thing removed")
        # @when("Thing updated")
        match = re.match(r"^Thing\s+(?P<action>added|removed|updated)$", target, re.IGNORECASE)
        if match is not None:
            event_names = {
                "added": "ThingAddedEvent",
                "removed": "ThingRemovedEvent",
                "updated": "ThingUpdatedEvent"
            }
            return cls(event_names.get(match.group('action')))


class DirectoryEventTrigger(Trigger):
    def __init__(self, path, event_kinds=[ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY], watch_subdirectories=False, trigger_name=None):
        trigger_name = validate_uid(trigger_name)
        configuration = {
            'path': path,
            'event_kinds': str(event_kinds),
            'watch_subdirectories': watch_subdirectories,
        }
        self.trigger = TriggerBuilder.create().withId(trigger_name).withTypeUID("jsr223.DirectoryEventTrigger").withConfiguration(Configuration(configuration)).build()

    firstWord = [ "directory", "subdirectory" ]
    @classmethod
    def parse(cls, target):
        # @when("Directory /opt/test [created, deleted, modified]")# requires S1566, 2.5M2 or newer
        # @when("Subdirectory 'C:\My Stuff' [created]")# requires S1566, 2.5M2 or newer
        match = re.match(r"^(?P<dirOrSub>Directory|Subdirectory)\s+(?P<path>'.+'|\S+)\s+\[(?P<options>(?:(?:,\s*)*(?:created|deleted|modified))+)\]$", target, re.IGNORECASE)
        if match is not None:
            event_kinds = []
            options = match.group('options').split()
            if "created" in options:
                event_kinds.append(ENTRY_CREATE)
            if "deleted" in options:
                event_kinds.append(ENTRY_DELETE)
            if "modified" in options:
                event_kinds.append(ENTRY_MODIFY)
            if event_kinds == []:
                event_kinds = [ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY]
            
            return cls(match.group('path'), event_kinds, (match.group('dirOrSub') == "Subdirectory"))

def when(target):
    """
    This function decorator creates a ``triggers`` attribute in the decorated
    function, which is used by the ``rule`` decorator when creating the rule.
    The ``when`` decorator simplifies the use of many of the triggers in this
    module and allows for them to be used with natural language similar to what
    is used in the rules DSL.
    """

    triggerClasses = [ StartupTrigger, CronTrigger, DateTimeTrigger, ItemStateUpdateTrigger, ItemStateChangeTrigger, ChannelEventTrigger,
                  ItemEventTrigger, ItemCommandTrigger, ThingStatusUpdateTrigger, ThingStatusChangeTrigger, ThingEventTrigger, DirectoryEventTrigger ]

    def parse(target):
        target = target.strip()

        firstWord = target.split()[0]

        for triggerClass in triggerClasses:
            # check first word to eliminate unecessary regex compiles
            if firstWord.lower() in triggerClass.firstWord:
                trigger = triggerClass.parse(target)
                if trigger is not None:
                    return trigger

        raise ValueError(u"Could not parse {} trigger: {}".format(firstWord, target))

    try:
        def whenFunction(function):
            triggerClasses = parse(target)

            if triggerClasses == None:
                raise ValueError(u"Invalid trigger: {}".format(target))

            if not hasattr(function, 'triggers'):
                function.triggers = []

            if isinstance(triggerClasses, list):
                for triggerClass in triggerClasses:
                    function.triggers.append(triggerClass.trigger)
            else:
                function.triggers.append(triggerClasses.trigger)

            return function

        return whenFunction

    except ValueError as ex:
        LOG.warn(ex)

        def bad_trigger(function):
            if not hasattr(function, 'triggers'):
                function.triggers = []
            function.triggers.append(None)
            return function

        # If there was a problem with a trigger configuration, then add None
        # to the triggers attribute of the callback function, so that
        # core.rules.rule can identify that there was a problem and not start
        # the rule
        return bad_trigger

    except:
        import traceback
        LOG.warn(traceback.format_exc())
