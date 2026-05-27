trigger AddOrderItem on Order (after insert) {
    // If the order Fulfilled_By__c field is null 
    if( Trigger.new[0].Fulfilled_By__c == null ) {
        // Call the GenerateOrderItemsHandler class's generate method and pass in the order(s
        GenerateOrderItemsHandler.generate((Order[])Trigger.new);
    }
}