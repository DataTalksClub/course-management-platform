import sys
import json


REGISTER_TASK_DEFINITION_EXCLUDED_FIELDS = (
    "status",
    "revision",
    "taskDefinitionArn",
    "requiresAttributes",
    "compatibilities",
    "registeredAt",
    "registeredBy",
)


def load_task_definition(input_file):
    with open(input_file, "r") as file:
        return json.load(file)["taskDefinition"]


def update_container_definitions(task_def, new_tag):
    container_definitions = task_def["containerDefinitions"]
    for container_def in container_definitions:
        update_container_image(container_def, new_tag)
        update_container_version(container_def, new_tag)


def update_container_image(container_def, new_tag):
    if "image" not in container_def:
        return

    image = container_def["image"]
    base_image, _ = image.split(":")
    container_def["image"] = f"{base_image}:{new_tag}"


def update_container_version(container_def, new_tag):
    environment = container_def.get("environment", [])
    version_var = None
    for env_var in environment:
        if env_var["name"] == "VERSION":
            version_var = env_var
            break

    if version_var is not None:
        version_var["value"] = new_tag
        return

    version_record = {"name": "VERSION", "value": new_tag}
    environment.append(version_record)


def remove_register_task_definition_fields(task_def):
    for field in REGISTER_TASK_DEFINITION_EXCLUDED_FIELDS:
        task_def.pop(field, None)


def write_task_definition(output_file, task_def):
    with open(output_file, "w") as file:
        json.dump(task_def, file, indent=4)


def update_task_definition(input_file, new_tag, output_file):
    """
    Update the image tag in the task definition and save to a new file.

    :param input_file: Path to the file containing the task definition JSON.
    :param new_tag: New tag to update the image with.
    :param output_file: Path to the file where the updated task definition will be saved.
    """

    print(
        f"Updating task definition from {input_file} with new tag {new_tag} "
        f"and saving to {output_file}"
    )

    try:
        task_def = load_task_definition(input_file)
        update_container_definitions(task_def, new_tag)
        remove_register_task_definition_fields(task_def)
        write_task_definition(output_file, task_def)

        print(f"Updated task definition saved to {output_file}")

    except FileNotFoundError:
        print(f"File not found: {input_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Invalid JSON input.")
        sys.exit(1)
    except KeyError:
        print("Invalid task definition structure.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python update_task_def.py "
            "<input_file> <new_tag> <output_file>"
        )
        sys.exit(1)

    argv = sys.argv
    update_task_definition(argv[1], argv[2], argv[3])
