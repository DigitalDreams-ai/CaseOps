trigger AHBDrChronoAccount on Account (after update) {
    AHBDrChronoAccountTriggerHandler.afterUpdate(Trigger.new, Trigger.oldMap);
}