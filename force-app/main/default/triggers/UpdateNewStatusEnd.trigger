trigger UpdateNewStatusEnd on Lead (before update) {
    for (Lead newLead : Trigger.new) {
        // Access the "old" record by its ID in Trigger.oldMap
        Lead oldLead = Trigger.oldMap.get(newLead.Id);
        
                  
        if(oldLead.Status == 'New'){
            newLead.New_Status_End__c = System.now();   
   
        }
        
        if(oldLead.Status == 'Open'){
            newLead.Open_Status_End__c = System.now();
            
        }
        
          if(oldLead.Status == 'Reactivated'){
            newLead.Reactivated_Status_End__c = System.now();
        }
        
        if(oldLead.Status == 'Qualifying'){
            newLead.Qualifying_Status_End__c = System.now();
            
        }
        
       
  }
}