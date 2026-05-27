trigger OppRollupTrigger on Opportunity (after insert, after update, before delete, after delete, after undelete) {
    // This will Run the rollup logic from the Apex rollup package
    Rollup.runFromTrigger();
}