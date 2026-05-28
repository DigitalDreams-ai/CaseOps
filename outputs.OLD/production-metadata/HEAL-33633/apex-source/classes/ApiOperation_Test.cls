@IsTest
public with sharing class ApiOperation_Test {
    private static final String TEST_OPERATION_NAME = 'UnitTest';

    @TestSetup
    static void makeData(){
        RecordType patientRT = [SELECT Id
                                FROM RecordType
                                WHERE SObjectType = 'Account'
                                AND DeveloperName = 'Patient_Account_Record_Type'];
        
        Account testAccount = new Account(
            FirstName = 'Test',
            LastName = 'McTesterson',
            RecordTypeId = patientRT.Id
        );
        insert testAccount;

        Id stdPriceBookId = Test.getStandardPricebookId();

        Opportunity testOpp = new Opportunity(
            AccountId = testAccount.Id,
            Name = 'Test',
            StageName = 'Prospecting',
            Pricebook2Id = stdPriceBookId,
            CloseDate = Date.today()
        );
        insert testOpp;

        Product2 testProduct = new Product2(
            Name = 'Test Product',
            IsActive = true,
            Display_Name__c = 'Test Product',
            Online_Store_URL__c = 'https://Online_store_URL.com',
            StockKeepingUnit = 'StockKeepingUnit'
        );
        Insert testProduct;

        PricebookEntry pbe =  new PricebookEntry(
            Pricebook2Id = stdPriceBookId,
            Product2Id = testProduct.Id,
            UnitPrice = 100.00,
            IsActive = true
        );
        Insert pbe;

        List<OpportunityLineItem> olis = new List<OpportunityLineItem>();
        OpportunityLineItem oli1 = new OpportunityLineItem(
            OpportunityId = testOpp.id,
            Quantity = 1,
            UnitPrice = 100.00,
            Product2Id = testProduct.Id
        );
        olis.add(oli1);

        OpportunityLineItem oli2 = new OpportunityLineItem(
            OpportunityId = testOpp.id,
            Quantity = 2,
            UnitPrice = 100.00,
            Product2Id = testProduct.Id
        );
        olis.add(oli2);

        insert olis;
    }

    @IsTest
    private static void shouldThrowException_ForTestOperation_WhenGivenInvalidOperation(){
        Account testAccount = [SELECT Id FROM Account WHERE Name = 'Test McTesterson'];
        Opportunity testOpp = [SELECT Id FROM Opportunity WHERE AccountId = :testAccount.Id];
        String expectedException = 'Improperly configured API callout. Validate accuracy of API Operation Name';
        Test.startTest();
        try{
            TestOperation testOperation = new TestOperation('FakeOperation', testOpp.Id);
            String failMsg = 'Should not have been a successful operation. Check if improperly pulling metadata or if FakeOperation record exists';
            Assert.isTrue(false, failMsg);
        } catch(Exception e){
            String failMsg = 'Should have thrown error due to fake operation. Check if different reference error';
            Assert.areEqual(expectedException, e.getMessage(), failMsg);
        }
        Test.stopTest();
    }

    @IsTest
    private static void shouldThrowException_ForTestOperation_WhenOperationHasNoParams(){
        Account testAccount = [SELECT Id FROM Account WHERE Name = 'Test McTesterson'];
        Opportunity testOpp = [SELECT Id FROM Opportunity WHERE AccountId = :testAccount.Id];
        String expectedException = 'No API Parameters defined for API Operation';
        Test.startTest();
        try{
            TestOperation testOperation = new TestOperation('API_Operation_No_Params_Test', testOpp.Id);
            String failMsg = 'Should not have been a successful operation. Check if improperly pulling params or if related params exists';
            Assert.isTrue(false, failMsg);
        } catch(Exception e){
            String failMsg = 'Should have thrown error due to no related params. Check if different reference error';
            Assert.areEqual(expectedException, e.getMessage(), failMsg);
        }
        Test.stopTest();
    }

    @IsTest
    private static void shouldBuildBodyParams_ForTestOperation_WhenOperationIsValidPOST(){
        Account testAccount = [SELECT Id FROM Account WHERE Name = 'Test McTesterson'];
        Opportunity testOpp = [SELECT Id FROM Opportunity WHERE AccountId = :testAccount.Id];
        Test.startTest();
        TestOperation testOperation = new TestOperation('API_Operation_POST_Test', testOpp.Id);
        Map<String,Object> bodyParams = testOperation.buildCallout();
        Test.stopTest();
        //This testing will be hardcoded as I cannot determine a reliable dynamic way 
        //to compare the metadata params to to the results at this time.
        String expectedStageNameParam = 'Prospecting';
        String stageNameFailMsg = 'Expected stageName to be singular string value of Prospecting. Check if value changed or if metadata is incorrect';
        Assert.areEqual(expectedStageNameParam, String.valueOf(bodyParams.get('stageName')), stageNameFailMsg);
        String expectedAccountParam = '{firstname=Test, lastname=McTesterson}';
        String accountFailMsg = 'Expected account to be an object of first and last name. Check if value changed or if metadata is incorrect';
        Assert.areEqual(expectedAccountParam, String.valueOf(bodyParams.get('account')), accountFailMsg);
        String expectedLineItemParam = '({quantity=1.00}, {quantity=2.00})';
        String lineItemFailMsg = 'Expected lineItem to be an object array with two values. Check if value changed or if metadata is incorrect';
        Assert.areEqual(expectedLineItemParam, String.valueOf(bodyParams.get('lineitems')), lineItemFailMsg);
    }


    @IsTest
    private static void shouldInvokeCallout_ForTestOperation_WhenOperationIsValidPOST(){
        Test.setMock(HttpCalloutMock.class, new TestOperationMock());
        Account testAccount = [SELECT Id FROM Account WHERE Name = 'Test McTesterson'];
        Opportunity testOpp = [SELECT Id FROM Opportunity WHERE AccountId = :testAccount.Id];
        Test.startTest();
        TestOperation testOperation = new TestOperation('API_Operation_POST_Test', testOpp.Id);
        testOperation.buildCallout();
        HttpResponse response = testOperation.invoke();
        Test.stopTest();

        Assert.areEqual(200, response.getStatusCode(), 'Expected successful response. Check asserts in Mock class');
    }

    public class TestOperationMock implements HttpCalloutMock{
        public HttpResponse respond(HttpRequest req){
            Boolean methodHandled = false;
            HttpResponse response = new HttpResponse();
            response.setStatusCode(200);
            Assert.areEqual('https://dummy.sfd/test', req.getEndpoint(), 'Check if endpoint is being formed correctly or if metadata changed');
            if(req.getMethod() == 'POST'){
                methodHandled = true;
                Assert.areNotEqual('', req.getBody(), 'Excepted body to be populated');
            }
            Assert.isTrue(methodHandled, 'Method was not handled in mock. Check if test missing or if metadata incorrect');
            // Send back a 200 as the assert statements should break testing if failed
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            return res;
        }
    }


    private class TestOperation extends ApiOperation{
        public TestOperation(String name, Id testRecordId){
            super(name, testRecordId);
        }
        
        public Map<String,Object> buildCallout(){
            this.buildBody();
            return this.jsonBody;
        }
        
        public HttpResponse invoke(){
           return this.invokeCallout();
        }
    }
}