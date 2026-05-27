trigger ProductImageTrigger on Product_Image__c (after insert, after update) {
    Set<Id> productIdsToUpdate = new Set<Id>();

    for (Product_Image__c pImg : Trigger.new) {        
            productIdsToUpdate.add(pImg.Product__c);
        }
    

    if (!productIdsToUpdate.isEmpty()) {
        List<Product2> productsToUpdate = [SELECT Id FROM Product2 WHERE Id IN :productIdsToUpdate];
        for (Product2 product : productsToUpdate) {
            product.Sync_executed__c = false; 
        }
        update productsToUpdate;
    }
}