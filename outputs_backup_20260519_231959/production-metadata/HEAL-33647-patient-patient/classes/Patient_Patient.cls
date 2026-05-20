public with sharing class Patient_Patient {
    @InvocableMethod(label='Internal API to create a patient' description='Creates a patient record in the system' category='Patient')
    public static void Submit_Patient(List<Request> requests) {
        // Go through each request and create a patient
        for(Request request: requests ) {
            // Clean the patient data
            // For gender we want to make sure it is Male or Female
            if(request.patient.gender != null) {
                String gender = request.patient.gender;
                if (gender.toLowerCase() == 'male') {
                    request.patient.gender = 'Male';
                } else {
                    request.patient.gender = 'Female';
                }
            }

            // For the date of birth convert from August 8, 2023 to YYYY-MM-DD
            // request.patient.birthdate is a Date
            if (request.patient.birthdate != null) {
                String[] dateParts = request.patient.birthdate.split(' ');
                String month = dateParts[0];
                String day = dateParts[1].replace(',','');
                String year = dateParts[2];
                String monthNumber = '01';
                if (month == 'January') {
                    monthNumber = '01';
                } else if (month == 'February') {
                    monthNumber = '02';
                } else if (month == 'March') {
                    monthNumber = '03';
                } else if (month == 'April') {
                    monthNumber = '04';
                } else if (month == 'May') {
                    monthNumber = '05';
                } else if (month == 'June') {
                    monthNumber = '06';
                } else if (month == 'July') {
                    monthNumber = '07';
                } else if (month == 'August') {
                    monthNumber = '08';
                } else if (month == 'September') {
                    monthNumber = '09';
                } else if (month == 'October') {
                    monthNumber = '10';
                } else if (month == 'November') {
                    monthNumber = '11';
                } else if (month == 'December') {
                    monthNumber = '12';
                }
                request.patient.birthdate = year + '-' + monthNumber + '-' + day;
            }

            //Set accountStatus to TRUE if it comes in as null
            if (request.patient.accountStatus == null) {
                request.patient.accountStatus = 'ACTIVE';
            }

            // Serialize the patient data and store it in the event
            request.event.data = JSON.serialize(request.patient, true);

            List<Patient_DS_Event> events = new List<Patient_DS_Event>();
            events.add(request.event);

            Id job = System.enqueueJob(new Patient_AsyncSalesforceEventsAPI(events));
            System.debug('Patient_Patient: job ' + job);
        }

    }

    public class Request {
        @InvocableVariable(label='Patient Details' description='APEX Defined Patient Information' required=true)
        public Patient_DS_Patient patient;
        @InvocableVariable(label='Event Details' description='APEX Defined Event Information' required=true)
        public Patient_DS_Event event;
    }

}