from uuid import uuid1

import click

from sceptre.context import SceptreContext
from sceptre.cli.helpers import catch_exceptions, confirmation
from sceptre.cli.helpers import write, stack_status_exit_code
from sceptre.cli.helpers import simplify_change_set_description
from sceptre.stack_status import StackChangeSetStatus
from sceptre.plan.plan import SceptrePlan

from sceptre.plan.executor import SceptrePlanExecutor


@click.command(name="update", short_help="Update a stack.")
@click.argument("path")
@click.option(
    "-c", "--change-set", is_flag=True,
    help="Create a change set before updating."
)
@click.option(
    "-v", "--verbose", is_flag=True, help="Display verbose output."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Assume yes to all questions."
)
@click.pass_context
@catch_exceptions
def update_command(ctx, path, change_set, verbose, yes):
    """
    Updates a stack for a given config PATH. Or perform an update via
    change-set when the change-set flag is set.
    \f

    :param path: Path to execute the command on.
    :type path: str
    :param change_set: Whether a change set should be created.
    :type change_set: bool
    :param verbose: A flag to print a verbose output.
    :type verbose: bool
    :param yes: A flag to answer 'yes' to all CLI questions.
    :type yes: bool
    """

    context = SceptreContext(
        command_path=path,
        project_path=ctx.obj.get("project_path"),
        user_variables=ctx.obj.get("user_variables"),
        options=ctx.obj.get("options"),
        output_format=ctx.obj.get("output_format"),
        ignore_dependencies=ctx.obj.get("ignore_dependencies")
    )

    plan = SceptrePlan(context)

    if change_set:
        plan.resolve(command=plan.create_change_set.__name__)

        for batch in plan.launch_order:
            change_set_name = "-".join(["change-set", uuid1().hex])
            try:
                plan_executor = SceptrePlanExecutor(plan.create_change_set.__name__, [batch])
                plan_executor.execute(change_set_name)

                plan_executor = SceptrePlanExecutor(plan.wait_for_cs_completion.__name__, [batch])
                statuses = plan_executor.execute(change_set_name)

                plan_executor = SceptrePlanExecutor(plan.describe_change_set.__name__, [batch])
                change_set_descriptions = plan_executor.execute(change_set_name)

                for stack in change_set_descriptions:
                    stack_change_set_description = change_set_descriptions[stack]
                    if not verbose:
                        stack_change_set_description = simplify_change_set_description(stack_change_set_description)
                        if statuses[stack] != StackChangeSetStatus.READY and not stack_change_set_description["Changes"]:
                            no_changes_log = "                      - %s No changes in change set: %s" % (stack.name, change_set_name)
                            write(no_changes_log)
                            continue
                    write(stack_change_set_description, context.output_format)

                stacks_to_update = [stack for stack in statuses if statuses[stack] == StackChangeSetStatus.READY and change_set_descriptions[stack]["Changes"]]

                if stacks_to_update:
                    if yes or click.confirm("Proceed with stack update of %s?" % [x.name for x in stacks_to_update]):
                        e = SceptrePlanExecutor(plan.execute_change_set.__name__, [stacks_to_update])
                        e.execute(change_set_name)
                    else:
                        exit(1)

            finally:
                executor = SceptrePlanExecutor(plan.delete_change_set.__name__, [batch])
                executor.execute(change_set_name)
    else:
        confirmation("update", yes, command_path=path)
        responses = plan.update()
        exit(stack_status_exit_code(responses.values()))
