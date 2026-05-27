trigger EmailMessageTrigger on EmailMessage (after insert) {
    if (Trigger.isAfter && Trigger.isInsert) {
        EmailMessageTriggerHandler.handleAfterInsert(Trigger.new);
    }
}