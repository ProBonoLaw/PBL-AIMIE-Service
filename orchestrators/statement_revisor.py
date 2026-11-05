from typing import Any, Generator, List
from azure.durable_functions import DurableOrchestrationContext, RetryOptions
from azure.durable_functions.models.Task import TaskBase

from AIInteractionService.generators.revision.types import RevisionRequest
from AIInteractionService.utils.partitioning_tools import get_partitions
from AIInteractionService.utils.section_extractor import get_substatements
from activities.types import AnswerWithSourcesResult, FactValidatorActivityResults, RevisionActivityRequest, revision_activity_name
from .progress import update_progress
from .types import StatementValidationRevisionOrchestrationRequest, StatementValidationRevisionOrchestrationResult, statement_revisor_orchestrator_name


class StatementRevisor:
    """
    A class to revise SQL statements.
    """

    def __init__(self,
                 activity_context: DurableOrchestrationContext,
                 location: str,
                 max_doc_count: int,
                 hearing_type: str,
                 account_id: str,
                 session_id: str):
        """
        Initialize the StatementRevisor.

        :param activity_context: The durable function context of the orchestrator.
        :param location: The location of the court hearing.
        :param max_doc_count: The maximum number of documents to consider.
        :param hearing_type: The type of hearing.
        :param account_id: The account ID of the user.
        :param session_id: The session ID of the user.
        """
        self.activity_context = activity_context
        self.location = location
        self.max_doc_count = max_doc_count
        self.hearing_type = hearing_type
        self.account_id = account_id
        self.session_id = session_id

    def review_and_revise(self, statement: str, actions_completed: int, actions_remaining: int, partition_statement: bool = True) -> Generator[Any, Any, tuple[str, List[FactValidatorActivityResults]]]:
        if not statement:
            raise ValueError("Statement cannot be empty")
        validation_requests: List[TaskBase] = []
        retry_options: RetryOptions = RetryOptions(1000, 3)
        actions = []
        index = 0
        sub_statements = list(get_substatements(statement)) if partition_statement else [(statement, statement)]
        length = len(sub_statements)
        for input_statement, original_input_statement in sub_statements:
            actions.append(f'Review and Revise Statement {index}')
            fact_validator_request = StatementValidationRevisionOrchestrationRequest(
                statement=input_statement,
                is_last_paragraph=True if index == length - 1 else False,
                original_input_statement=original_input_statement,
                original_request=statement,
                location=self.location,
                max_doc_count=self.max_doc_count,
                hearing_type=self.hearing_type,
                account_id=self.account_id,
                session_id=self.session_id)
            child_id = f"{self.activity_context.instance_id}:{index}"
            fact_validator_activity_result = self.activity_context.call_sub_orchestrator_with_retry(
                statement_revisor_orchestrator_name,
                retry_options,
                fact_validator_request,
                child_id)
            validation_requests.append(fact_validator_activity_result)
            index += 1

        actions_remaining += index

        self.activity_context.set_custom_status(
            {'actionsCompleted': actions_completed, 'actionsRemaining': actions_remaining, 'actionsToComplete': actions})
        validation_partitions = get_partitions(validation_requests, 10)

        validation_results: List[StatementValidationRevisionOrchestrationResult] = [
        ]
        for partition in validation_partitions:
            partition_results: List = yield self.activity_context.task_all(partition)
            actions_completed, actions_remaining = update_progress(
                self.activity_context,
                actions,
                actions_completed,
                actions_remaining,
                len(partition_results))
            validated_statements = [
                StatementValidationRevisionOrchestrationResult.model_validate(
                    result)
                for result in partition_results
            ]
            validation_results.extend(validated_statements)

        final_answer = self.__process_validation_results(
            statement, validation_results)

        if final_answer != statement:
            revision: AnswerWithSourcesResult = yield self.activity_context.call_activity_with_retry(
                revision_activity_name,
                retry_options,
                RevisionActivityRequest(
                    input=final_answer,
                    statement=final_answer,
                    use_retrievers=False,
                    location=self.location,
                    max_doc_count=self.max_doc_count,
                    hearing_type=self.hearing_type,
                    account_id=self.account_id,
                    session_id=self.session_id,
                    feedback="Revise so that the statement flows better.  Do not add any new "
                    "information, just rearrange the existing information. "
                    "Make sure to keep the details and meaning of the statement intact."))
            final_answer = revision.answer

        return final_answer, [x.validation_status for x in validation_results]

    def __process_validation_results(self,
                                     original_statement: str,
                                     validation_results: List[StatementValidationRevisionOrchestrationResult]) -> str:
        """
        Process the validation results and generate a final answer.

        :param original_statement: The original statement to be processed.
        :param validation_results: The results of the validation.
        :return: The final answer after processing the validation results.
        """
        final_answer = original_statement
        footer = ""
        for i in range(len(validation_results)):
            statement_validation_result = validation_results[i]
            was_revised = statement_validation_result.was_revised
            original_substatement = statement_validation_result.original_input_statement
            validation_result = statement_validation_result.validation_status
            if was_revised:
                revised_substatement = statement_validation_result.revised_statement
                if (validation_result.is_valid == False and not revised_substatement):
                    if validation_result.is_not_found_in_context == True:
                        final_answer = final_answer.replace(
                            validation_result.raw_original_statement.strip(), "")
                        footer += f"\n\n### Invalid Data {i+1}. _{original_substatement}_\n\n**Explanation:**\n{validation_result.answer}\n\n**Source:**\n{validation_result.contradiction_source}"
                        continue
                    footer += f"\n\n### Possible Discrepancy {i+1}. _{original_substatement}_\n\n**Explanation:**\n{validation_result.answer}\n\n**Source:**\n{validation_result.contradiction_source}"
                else:
                    if not revised_substatement:
                        footer += f"\n\n### Possible Discrepancy {i+1}. _{original_substatement}_\n\n**Explanation:**\n{validation_result.answer}\n\n**Source:**\n{validation_result.contradiction_source}"
                        continue
                    prior_answer = final_answer
                    final_answer = final_answer.replace(original_substatement.strip(
                    ), revised_substatement.strip())
                    if final_answer != prior_answer:
                        footer += f"\n\n### Replacement {i+1}.\n\n**Original Statement:** _{original_substatement}_\n\n**New Statement:** _{revised_substatement}_\n\n**Explanation:**\n{validation_result.answer}\n\n**Source:**\n{validation_result.contradiction_source}"
                    else:
                        footer += f"\n\n### Recommended Data Change {i+1}. _{original_substatement}_\n\n**Explanation:**\n{validation_result.answer}\n\n**Source:**\n{validation_result.contradiction_source}"

        if len(footer) > 0:
            final_answer = "# Answer\n" + final_answer + "\n\n## Footer\n" + footer
        return final_answer
