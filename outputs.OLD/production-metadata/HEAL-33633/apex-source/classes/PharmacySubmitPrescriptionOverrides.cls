public without sharing class PharmacySubmitPrescriptionOverrides implements Callable{
    public Object call(String methodName, Map<String, Object> arguments){
        switch on methodName{
            when 'dosingOverride'{
                return dosingOverride(arguments);
            } when 'quantityOverride'{
                return quantityOverride(arguments);
            } when else{
                throw new ApiOverrideException('Bad Override');
            }
        }
    }

    private Object dosingOverride(Map<String, Object> arguments){
        String uuid = (String)arguments.get('UUID__c');
        OrderItem item = [SELECT Id,
                                Dose__c,
                                Frequency_Schedule__c
                        FROM OrderItem
                        WHERE UUID__c = :uuid];
        List<Map<String, Object>> dosing = new List<Map<String, Object>>();
        Map<String, Object> dosingAttributes = new Map<String, Object>();
        if(item.Dose__c == null || item.Frequency_Schedule__c == null){
            throw new ApiOverrideException('Dosing and Frequency Schedule must be set on Order Product');
        }
        dosingAttributes.put('Dosing', Double.valueOf(item.Dose__c));
        dosingAttributes.put('DosingFrequency', item.Frequency_Schedule__c);
        dosing.add(dosingAttributes);

        return dosing;
    }

    private Object quantityOverride(Map<String, Object> arguments){
        String uuid = (String)arguments.get('UUID__c');
        OrderItem item = [SELECT Id,
                                Quantity
                        FROM OrderItem
                        WHERE UUID__c = :uuid];
        Map<String, Object> quantity = new Map<String, Object>();
        if(item.Quantity == null){
            throw new ApiOverrideException('Quantity must be set on Order Product');
        }
        Integer quantityInt = Integer.valueOf(item.Quantity);
        return quantityInt;
    }
    
    public class ApiOverrideException extends Exception {}    
}