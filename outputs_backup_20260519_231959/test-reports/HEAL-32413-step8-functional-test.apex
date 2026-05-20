String runId = String.valueOf(Datetime.now().getTime());

RecordType labsRt = [
    SELECT Id, DeveloperName
    FROM RecordType
    WHERE SobjectType = 'Opportunity'
    AND DeveloperName = 'Lab_Opportunity_Record_Type'
    LIMIT 1
];

Account patient = new Account(Name = 'ZZ HEAL-32413 Test Patient ' + runId);
insert patient;

Account lab = new Account(Name = 'ZZ HEAL-32413 Test Lab ' + runId);
insert lab;

Opportunity opp = new Opportunity(
    Name = 'ZZ HEAL-32413 Labs Approval Test ' + runId,
    AccountId = patient.Id,
    RecordTypeId = labsRt.Id,
    StageName = 'Open',
    CloseDate = Date.today().addDays(7),
    Lab_Name__c = lab.Id
);
insert opp;

System.debug('HEAL32413_TEST_OPPORTUNITY_ID=' + opp.Id);
System.debug('HEAL32413_INITIAL_LOCKED=' + Approval.isLocked(opp.Id));

Approval.ProcessSubmitRequest submitRequest = new Approval.ProcessSubmitRequest();
submitRequest.setObjectId(opp.Id);
submitRequest.setComments('HEAL-32413 Step 8 functional test submit.');
submitRequest.setProcessDefinitionNameOrId('Opportunity_Approval_Process_Labs');
Approval.ProcessResult submitResult = Approval.process(submitRequest);

System.debug('HEAL32413_SUBMIT_SUCCESS=' + submitResult.isSuccess());
System.debug('HEAL32413_SUBMIT_INSTANCE_STATUS=' + submitResult.getInstanceStatus());
System.debug('HEAL32413_AFTER_SUBMIT_LOCKED=' + Approval.isLocked(opp.Id));

List<ProcessInstanceWorkitem> workItems = [
    SELECT Id, ActorId, ProcessInstanceId
    FROM ProcessInstanceWorkitem
    WHERE ProcessInstance.TargetObjectId = :opp.Id
    LIMIT 1
];

if (!workItems.isEmpty()) {
    Approval.ProcessWorkitemRequest approveRequest = new Approval.ProcessWorkitemRequest();
    approveRequest.setWorkitemId(workItems[0].Id);
    approveRequest.setAction('Approve');
    approveRequest.setComments('HEAL-32413 Step 8 functional test approve.');
    Approval.ProcessResult approveResult = Approval.process(approveRequest);
    System.debug('HEAL32413_APPROVE_SUCCESS=' + approveResult.isSuccess());
    System.debug('HEAL32413_APPROVE_INSTANCE_STATUS=' + approveResult.getInstanceStatus());
} else {
    System.debug('HEAL32413_APPROVE_SKIPPED_NO_WORKITEM=true');
}

Opportunity afterApproval = [
    SELECT Id, StageName, Lab_Name__c
    FROM Opportunity
    WHERE Id = :opp.Id
];

System.debug('HEAL32413_AFTER_APPROVAL_STAGE=' + afterApproval.StageName);
System.debug('HEAL32413_AFTER_APPROVAL_LOCKED=' + Approval.isLocked(opp.Id));

Account lab2 = new Account(Name = 'ZZ HEAL-32413 Test Lab Updated ' + runId);
insert lab2;

afterApproval.Lab_Name__c = lab2.Id;

try {
    update afterApproval;
    System.debug('HEAL32413_LAB_NAME_UPDATE_SUCCESS=true');
} catch (Exception error) {
    System.debug('HEAL32413_LAB_NAME_UPDATE_SUCCESS=false');
    System.debug('HEAL32413_LAB_NAME_UPDATE_ERROR=' + error.getMessage());
}

Opportunity finalOpp = [
    SELECT Id, StageName, Lab_Name__c
    FROM Opportunity
    WHERE Id = :opp.Id
];

System.debug('HEAL32413_FINAL_STAGE=' + finalOpp.StageName);
System.debug('HEAL32413_FINAL_LOCKED=' + Approval.isLocked(opp.Id));
System.debug('HEAL32413_FINAL_LAB_NAME=' + finalOpp.Lab_Name__c);
