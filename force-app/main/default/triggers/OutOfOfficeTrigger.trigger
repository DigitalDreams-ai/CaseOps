trigger OutOfOfficeTrigger on tdc_tsw__Message__c (after insert) {
if(trigger.isAfter && trigger.isInsert){
      try{
      tdc_tsw__SMSIncomingAlert__c AutoReplyTrigger = tdc_tsw__SMSIncomingAlert__c.getInstance('AutoReplyTrigger');
      if(AutoReplyTrigger==null){
      OutOfOfficeHandler.onAfterInsert(trigger.new);
       }
      }catch(Exception ex){
            System.debug(ex);
        }
      } 
}