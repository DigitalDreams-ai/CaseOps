/**
 * @description: Unified trigger for OrderProduct (OrderItem) using Trigger Actions Framework
 * @testclass : OrderProductTriggerActionTest
 * @last modified on: 09-10-2025
 * @last modified by: srodrigues@10xhealthsystem.com
 **/

trigger OrderProductTrigger on OrderItem(
    before insert,
    after insert,
    before update,
    after update,
    before delete,
    after delete,
    after undelete
) {
    new MetadataTriggerHandler().run();
}