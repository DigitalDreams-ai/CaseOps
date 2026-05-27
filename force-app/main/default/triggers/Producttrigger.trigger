// trigger Producttrigger on Product2 (after insert, after update) {
//     Set<Id> insertedProdIdSet = new Set<Id>();
//     Set<Id> updatedProdIdSet = new Set<Id>();
//     Set<Id> createProdIdSet = new Set<Id>();

    
//     if (Trigger.isInsert) {
//         for (Product2 prod : Trigger.new) {       
//             insertedProdIdSet.add(prod.Id);
//         }

//         if (!insertedProdIdSet.isEmpty()) {
//             if(!Test.isRunningTest()){
//             CreateProductCallout.createProduct(insertedProdIdSet);
//             }
//         }
//     } else if (Trigger.isUpdate) {
//         for (Product2 prod : Trigger.new) {            
//             Product2 oldProd = Trigger.oldMap.get(prod.Id);
            
//                 if (prod.Last_Successful_Sync__c == null) {
//                     // Add to creation set if Last_Successful_Sync__c is empty
//                     createProdIdSet.add(prod.Id);
//                 } else {
//                     // Add to update set if Last_Successful_Sync__c is not empty
//                     updatedProdIdSet.add(prod.Id);
//                 }
            
//         }

//         if (!createProdIdSet.isEmpty()) {
//             if(!Test.isRunningTest()){
//             CreateProductCallout.createProduct(createProdIdSet);
//             }
//         }
//         if (!updatedProdIdSet.isEmpty()) {
//             if(!Test.isRunningTest()){
//             UpdateProductCallout.updateProduct(updatedProdIdSet);
//             }
//         }
//     }

// }

trigger Producttrigger on Product2 (after insert, after update) {
    Set<Id> insertedProdIdSet = new Set<Id>();
    Set<Id> updatedProdIdSet = new Set<Id>();
    Set<Id> createProdIdSet = new Set<Id>();
    
    if (CheckRecursion.runOnce()) {
        try {
            if (Trigger.isInsert) {
                for (Product2 prod : Trigger.new) {
                    insertedProdIdSet.add(prod.Id);
                }

                if (!insertedProdIdSet.isEmpty()) {
                    if (!Test.isRunningTest()) {
                        System.debug('Calling CreateProductCallout.createProduct with insertedProdIdSet.');
                        CreateProductCallout.createProduct(insertedProdIdSet);
                    }
                }
            } else if (Trigger.isUpdate) {
                for (Product2 prod : Trigger.new) {
                    Product2 oldProd = Trigger.oldMap.get(prod.Id);

                    if (!(oldProd.Sync_executed__c == false && prod.Sync_executed__c == true) && prod.Last_Successful_Sync__c == null) {
                        createProdIdSet.add(prod.Id);
                    } else {
                        if (!(oldProd.Sync_executed__c == false && prod.Sync_executed__c == true)) {
                            updatedProdIdSet.add(prod.Id);
                        }
                    }
                }

                if (!createProdIdSet.isEmpty()) {
                    if (!Test.isRunningTest()) {
                        System.debug('Calling CreateProductCallout.createProduct with createProdIdSet.');
                        CreateProductCallout.createProduct(createProdIdSet);
                    }
                }
                if (!updatedProdIdSet.isEmpty()) {
                    if (!Test.isRunningTest()) {
                        System.debug('Calling UpdateProductCallout.updateProduct with updatedProdIdSet.');
                        UpdateProductCallout.updateProduct(updatedProdIdSet);
                    }
                }
            }
        } catch (Exception e) {
            System.debug('Exception: ' + e.getMessage());
        } finally {
            CheckRecursion.resetRun();
        }
    } else {
        System.debug('Trigger execution skipped due to recursion check.');
    }
}