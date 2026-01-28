import os
import uuid
from time import sleep
from typing import Any, Dict

import cfnresponse
from common.database import save_game_source, save_npc_background
from common.google_spreadsheet import get_npc_background_google_spreadsheet


def lambda_handler(event: Dict[str, Any], context: Any) -> None:

    print(event)
    response_url = event.get("ResponseURL", "")
    stack_id = event.get("StackId", "")
    request_id = event.get("RequestId", "")
    logical_resource_id = event.get("LogicalResourceId", "")
    physical_resource_id = event.get("PhysicalResourceId", "")

    print(
        f'curl -H "Content-Type: \'\'" -X PUT -d \'{{"Status": "SUCCESS","PhysicalResourceId": "{physical_resource_id}","StackId": "{stack_id}","RequestId": "{request_id}","LogicalResourceId": "{logical_resource_id}"}}\' "{response_url}"'
    )
    wait_seconds = 0
    uid = str(uuid.uuid1())
    if event["RequestType"] in ["Create", "Update"]:
        wait_seconds = int(event["ResourceProperties"].get("WaitSeconds", 0))

    sleep(wait_seconds)
    response = {"TimeWaited": wait_seconds, "Id": uid}
    if event["RequestType"] == "Create":
        try:
            npc_background_sheet_id = os.environ.get("NCPBackgroundSheetId")
            npc_backgrounds = get_npc_background_google_spreadsheet(
                npc_background_sheet_id
            )
            if not npc_backgrounds:
                reason = "Failed to retrieve NPC backgrounds from the spreadsheet."
                response["Reason"] = reason
                cfnresponse.send(
                    event, context, cfnresponse.FAILED, response, "Waiter-" + uid
                )
                return
            for npc in npc_backgrounds:
                save_npc_background(
                    npc["name"], npc["age"], npc["gender"], npc["background"]
                )
            save_game_source(
                "game01",
                "https://github.com/practical-bootcamp/k8s-game-rule/archive/refs/heads/main.zip",
            )
        except (KeyError, ValueError, IOError) as e:
            reason = f"Failed: {str(e)}"
            response["Reason"] = reason
            cfnresponse.send(
                event, context, cfnresponse.FAILED, response, "Waiter-" + uid
            )
            return

    cfnresponse.send(event, context, cfnresponse.SUCCESS, response, "Waiter-" + uid)
