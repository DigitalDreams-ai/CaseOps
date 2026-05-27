trigger AssignPriceBookToOrder on Order (before insert, before update) {
    // If the Fulfilled_By__c field is not null, then the Price Book should be set to the Account Price Book
    // If the Fulfilled_By__c field is null don't do anything
    Boolean setPriceBook = true;
    for (Order po1 : Trigger.new) {
        if (po1.Fulfilled_By__c != null) {
            setPriceBook = false;
            break;
        }
    }

    if (setPriceBook) {
        PriceBook2[] priceBooks = [SELECT Id, Account_Price_Book__c FROM PriceBook2 WHERE IsActive = true];
        Map<Id, PriceBook2> pbMap = new Map<Id, PriceBook2>();
        for (PriceBook2 priceBook : priceBooks) {
            if (priceBook.Account_Price_Book__c != null && !pbMap.containsKey(priceBook.Account_Price_Book__c))
                pbMap.put(priceBook.Account_Price_Book__c, priceBook);
        }
        
        for (Order po : Trigger.new) {
            PriceBook2 priceBook = pbMap.get(po.Vendor_Name__c);
            if (priceBook != null)
                po.PriceBook2Id = priceBook.Id;
        }
    }

}