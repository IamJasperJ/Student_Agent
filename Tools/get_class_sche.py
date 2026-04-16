from network_block.ScheduleGet.getSchedule import getSchedule
import json
def get_class_sche(update_force: bool = False):
    sche = getSchedule(update_force)
    return json.dumps(sche, ensure_ascii=False)

GETSCHE_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "get_class_sche",
        "description": "Get class Schedule.",
        "parameters": {
            "type": "object",
            "properties": {
                "update_force": {
                    "type": "boolean",
                    "description": "If set to true, forces the system to bypass local cache"
                        " and scrape the latest schedule directly from the educational portal."
                        " This operation is resource-intensive and should only be triggered " 
                        "when the user explicitly says."
                },
            },
            "required": []
        }
    }
}
