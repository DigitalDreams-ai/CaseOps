/**
 * @description: This class provides validation for Pharmacy Order submissions before calling the external API. It validates all required fields for the Submit Prescription callout and returns detailed error messages for missing fields.
 * @last modified on: 09-29-2025
 * @last modified by: srodrigues@10xhealthsystem.com
 **/

public with sharing class PharmacyOrderValidation {
    @InvocableMethod(label='Validate Pharmacy Order' description='Validates required fields for Pharmacy Order submission' category='Order')
    public static List<ValidationResult> validatePharmacyOrder(List<ValidationRequest> requests) {
        // Check CRUD permissions before executing queries
        ValidationResult permissionResult = checkCrudPermissions();
        if (permissionResult != null) {
            return new List<ValidationResult>{ permissionResult };
        }

        List<ValidationResult> results = new List<ValidationResult>();

        for (ValidationRequest request : requests) {
            ValidationResult result = processValidationRequest(request);
            results.add(result);
        }

        return results;
    }

    /**
     * @description Check CRUD permissions for required objects
     * @return ValidationResult with error if permissions insufficient, null if permissions OK
     */
    private static ValidationResult checkCrudPermissions() {
        if (!Schema.sObjectType.Order.isAccessible()) {
            return createPermissionErrorResult('Insufficient permissions to access Order records');
        }

        if (!Schema.sObjectType.Account.isAccessible()) {
            return createPermissionErrorResult('Insufficient permissions to access Account records');
        }

        if (!Schema.sObjectType.OrderItem.isAccessible()) {
            return createPermissionErrorResult('Insufficient permissions to access OrderItem records');
        }

        return null;
    }

    /**
     * @description Create permission error result
     * @param errorMessage The error message to display
     * @return ValidationResult with permission error
     */
    private static ValidationResult createPermissionErrorResult(String errorMessage) {
        ValidationResult result = new ValidationResult();
        result.isValid = false;
        result.errorMessages = new List<String>{ errorMessage };
        result.errorMessageSummary = errorMessage;
        return result;
    }

    /**
     * @description Process a single validation request
     * @param request The validation request to process
     * @return ValidationResult for the request
     */
    private static ValidationResult processValidationRequest(ValidationRequest request) {
        ValidationResult result = new ValidationResult();
        result.isValid = true;
        result.errorMessages = new List<String>();

        try {
            // Query the Order with all required fields
            Order orderRecord = getOrderWithRequiredFields(request.orderId);

            if (orderRecord == null) {
                result.isValid = false;
                result.errorMessages.add('Order record not found');
                result.errorMessageSummary = 'Order record not found';
                return result;
            }

            // Validate Order level fields
            validateOrderFields(orderRecord, result);

            // Validate Order Items
            validateOrderItems(orderRecord.Id, result);

            // Log validation results
            logValidationResults(result, orderRecord.Id);
        } catch (Exception e) {
            result.isValid = false;
            result.errorMessages.add('Validation error: ' + e.getMessage());
            Nebula.Logger.error('Pharmacy Order validation exception: ' + e.getMessage(), request.orderId);
        } finally {
            Nebula.Logger.saveLog();
        }

        // Set error message summary for Flow display
        setErrorMessageSummary(result);

        return result;
    }

    /**
     * @description Log validation results for audit trail
     * @param result The validation result
     * @param orderId The Order ID for logging context
     */
    private static void logValidationResults(ValidationResult result, Id orderId) {
        if (!result.isValid) {
            Nebula.Logger.warn('Pharmacy Order validation failed: ' + String.join(result.errorMessages, '; '), orderId);
        } else {
            Nebula.Logger.info('Pharmacy Order validation successful', orderId);
        }
    }

    /**
     * @description Set error message summary for Flow display
     * @param result The validation result to update
     */
    private static void setErrorMessageSummary(ValidationResult result) {
        if (result.errorMessages != null && !result.errorMessages.isEmpty()) {
            result.errorMessageSummary = String.join(result.errorMessages, '\n• ');
        } else {
            result.errorMessageSummary = '';
        }
    }

    /**
     * @description Query Order with all required fields for validation
     * @param orderId The Order Id to query
     * @return Order record with required fields
     */
    private static Order getOrderWithRequiredFields(Id orderId) {
        try {
            return [
                SELECT
                    Id,
                    UUID__c,
                    Shipping_Street__c,
                    Shipping_City__c,
                    Shipping_State__c,
                    Shipping_Zip_Code__c,
                    Account.Name,
                    Account.UUID__c,
                    Account.FirstName,
                    Account.LastName,
                    Account.DateOfBirth__c,
                    Account.Gender__c,
                    Signing_Practitioner__r.Name,
                    Signing_Practitioner__r.Phone,
                    Practitioner_Phone__c
                FROM Order
                WHERE Id = :orderId
                LIMIT 1
            ];
        } catch (QueryException e) {
            Nebula.Logger.error('Failed to query Order for validation: ' + e.getMessage(), orderId);
            return null;
        }
    }

    /**
     * @description Validate Order level required fields
     * @param orderRecord The Order record to validate
     * @param result The validation result to update
     */
    private static void validateOrderFields(Order orderRecord, ValidationResult result) {
        validateOrderBasicFields(orderRecord, result);
        validateAccountFields(orderRecord, result);
        validateShippingFields(orderRecord, result);
        validateSigningPractitionerFields(orderRecord, result);
    }

    /**
     * @description Validate basic Order fields
     */
    private static void validateOrderBasicFields(Order orderRecord, ValidationResult result) {
        validateRequiredField(orderRecord.UUID__c, getFieldLabel(Order.UUID__c), result);
    }

    /**
     * @description Validate Account related fields
     */
    private static void validateAccountFields(Order orderRecord, ValidationResult result) {
        validateRequiredField(orderRecord.Account.Name, getFieldLabel(Account.Name), result);
        validateRequiredField(orderRecord.Account.UUID__c, getFieldLabel(Account.UUID__c), result);
        validateRequiredField(orderRecord.Account.FirstName, 'Patient First Name', result);
        validateRequiredField(orderRecord.Account.LastName, 'Patient Last Name', result);
        validateRequiredField(orderRecord.Account.Gender__c, 'Patient Gender', result);

        if (orderRecord.Account.DateOfBirth__c == null) {
            result.isValid = false;
            result.errorMessages.add('Patient Date of Birth is required.');
        }
    }

    /**
     * @description Validate shipping address fields
     */
    private static void validateShippingFields(Order orderRecord, ValidationResult result) {
        validateRequiredField(orderRecord.Shipping_Street__c, getFieldLabel(Order.Shipping_Street__c), result);
        validateRequiredField(orderRecord.Shipping_City__c, getFieldLabel(Order.Shipping_City__c), result);
        validateRequiredField(orderRecord.Shipping_State__c, getFieldLabel(Order.Shipping_State__c), result);
        validateRequiredField(orderRecord.Shipping_Zip_Code__c, getFieldLabel(Order.Shipping_Zip_Code__c), result);
    }

    /**
     * @description Validate signing practitioner fields
     */
    private static void validateSigningPractitionerFields(Order orderRecord, ValidationResult result) {
        if (orderRecord.Signing_Practitioner__r == null) {
            result.isValid = false;
            result.errorMessages.add(getFieldLabel(Order.Signing_Practitioner__c) + ' is required.');
            return;
        }

        validateRequiredField(orderRecord.Signing_Practitioner__r.Name, getFieldLabel(Account.Name), result);
        validateRequiredField(orderRecord.Signing_Practitioner__r.Phone, 'Signing Practitioner Phone', result);
    }

    /**
     * @description Helper method to validate required string fields using field labels
     */
    private static void validateRequiredField(String fieldValue, String fieldLabel, ValidationResult result) {
        if (String.isBlank(fieldValue)) {
            result.isValid = false;
            result.errorMessages.add(fieldLabel + ' is required.');
        }
    }

    /**
     * @description Get field label for a given SObject field
     */
    private static String getFieldLabel(Schema.SObjectField field) {
        return field.getDescribe().getLabel();
    }

    /**
     * @description Validate Order Items required fields
     * @param orderId The Order Id to query items for
     * @param result The validation result to update
     */
    private static void validateOrderItems(Id orderId, ValidationResult result) {
        List<OrderItem> orderItems = [
            SELECT
                Id,
                UUID__c,
                NDC__c,
                PricebookEntry.Product2Id,
                PricebookEntry.Product2.Name,
                Delivery_of_Dosage__c,
                Days_Supply__c,
                Dose__c,
                Units__c,
                Frequency_Schedule__c
            FROM OrderItem
            WHERE OrderId = :orderId
        ];

        if (orderItems.isEmpty()) {
            result.isValid = false;
            result.errorMessages.add('At least one Order Item is required');
            return;
        }

        for (OrderItem item : orderItems) {
            validateSingleOrderItem(item, result);
        }
    }

    /**
     * @description Validate a single Order Item and add individual error messages
     * @param item The OrderItem to validate
     * @param result The validation result to update
     */
    private static void validateSingleOrderItem(OrderItem item, ValidationResult result) {
        String productIdentifier = item.PricebookEntry.Product2.Name != null
            ? item.PricebookEntry.Product2.Name
            : 'Product ID: ' + item.PricebookEntry.Product2Id;
        String itemPrefix = productIdentifier + ': ';

        // OrderItem UUID
        if (String.isBlank(item.UUID__c)) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.UUID__c) + ' is required.');
        }

        // OrderItem NDC
        if (String.isBlank(item.NDC__c)) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.NDC__c) + ' is required.');
        }

        // Delivery of Dosage
        if (String.isBlank(item.Delivery_of_Dosage__c)) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.Delivery_of_Dosage__c) + ' is required.');
        }

        // Days Supply
        if (item.Days_Supply__c == null) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.Days_Supply__c) + ' is required.');
        }

        // Dose Amount
        if (item.Dose__c == null) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.Dose__c) + ' is required.');
        }

        // Dose Units
        if (String.isBlank(item.Units__c)) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.Units__c) + ' is required.');
        }

        // Frequency Schedule
        if (String.isBlank(item.Frequency_Schedule__c)) {
            result.isValid = false;
            result.errorMessages.add(itemPrefix + getFieldLabel(OrderItem.Frequency_Schedule__c) + ' is required.');
        }
    }

    /**
     * @description Request wrapper for validation
     */
    public class ValidationRequest {
        @InvocableVariable(label='Order Id' description='Id of the Order to validate' required=true)
        public Id orderId;
    }

    /**
     * @description Result wrapper for validation
     */
    public class ValidationResult {
        @InvocableVariable(label='Is Valid' description='Whether the Order passes validation')
        public Boolean isValid;

        @InvocableVariable(label='Error Messages' description='List of validation error messages')
        public List<String> errorMessages;

        @InvocableVariable(label='Error Message Summary' description='Concatenated error messages for display')
        public String errorMessageSummary;
    }
}