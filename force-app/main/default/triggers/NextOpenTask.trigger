trigger NextOpenTask on Task (after delete, after insert, after undelete, after update) {
  
  NextOpenTaskHandler.setDueDateOnRelatedObject(Trigger.newMap, Trigger.oldMap);
/*
  Set<Id> whoIds = new Set<Id>();
  if (Trigger.new != null) {
    for (Task task : Trigger.new) {
      if (!whoIds.contains(task.WhoId) && task.WhoId != null)
        whoIds.add(task.WhoId);
    }
  }
  
  if (Trigger.old != null) {
    for (Task task : Trigger.old) {
      if (!whoIds.contains(task.WhoId) && task.WhoId != null)
        whoIds.add(task.WhoId);
    }
  }
  
  AggregateResult[] results = [SELECT MIN(Due_Date__c) MinDueDate, WhoId FROM Task WHERE WhoId IN :whoIds AND Status <> 'Completed' GROUP BY WhoId];
  List<Sobject> sobjects = new List<Sobject>();
  for (AggregateResult result : results) {
    Id objectId = (Id)result.get('WhoId');
    Sobject o = null;
    if (objectId != null && String.valueOf(objectId).startsWith('00Q'))
    o = Lead.getSobjectType().newSobject(objectId);
    else if (objectId != null && String.valueOf(objectId).startsWith('003'))
    o = Contact.getSobjectType().newSobject(objectId);
    else
    continue;
    o.put('Next_Task_Due_Date__c', (Date)result.get('MinDueDate'));
    sobjects.add(o);
      }
      update sobjects;*/
   }