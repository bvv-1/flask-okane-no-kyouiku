from flask import Flask, jsonify, request
from flask_cors import CORS
import random
import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

app = Flask(__name__)
app.json.ensure_ascii = False  # NOTE: 日本語文字化け対策
CORS(app)

# .envファイルの内容を読み込む
load_dotenv()
SUPABASE_PROJECT_URL: str = os.getenv("SUPABASE_PROJECT_URL")
SUPABASE_API_KEY: str = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(
    supabase_url=SUPABASE_PROJECT_URL, supabase_key=SUPABASE_API_KEY
)


@app.route("/")
def hello_world():
    """
    API Endpoint: /
    HTTP Method: GET

    Get a simple "Hello, World!" message.

    Request:
    - Method: GET

    Response:
    - Success (HTTP 200 OK):
        {
            "message": "Hello, World!"
        }
    """
    data = {"message": "Hello, World!"}
    return jsonify(data), 200


@app.route("/api/v2/plans/suggest", methods=["POST"])
def suggest_plans_v2():
    """
    API Endpoint: /api/v1/plans/suggest
    HTTP Method: POST

    Generate suggested daily plans based on the user's goal and tasks.

    Request:
    - Method: POST
    - Headers:
        Content-Type: application/json
    - Body (JSON):
        {
            "goal": "computer",
            "goal_points": 100,
            "tasks": [
                {"task": "cleaning", "point": 5},
                {"task": "wash dishes", "point": 2}
            ]
        }

    Response:
    - Success (HTTP 200 OK):
        {
            "plans": [
                {"day": 1, "plans_today": [{"task": "cleaning", "point": 5}, ...]},
                {"day": 2, "plans_today": []},
            ]
        }
    - Bad Request (HTTP 400 Bad Request):
        {
            "error": "Invalid data format"
        }
    """

    try:
        # POSTリクエストのボディからJSONデータを取得
        request_data = request.get_json()

        # 必要なデータが揃っているか確認
        if not (
            "goal" in request_data
            and "goal_points" in request_data
            and "tasks" in request_data
        ):
            # 必要なデータが見つからない場合はエラーメッセージを返す
            return jsonify({"error": "Invalid data format"}), 400
        
        goal = request_data["goal"]
        goal_points = request_data["goal_points"]
        tasks = request_data["tasks"]


        # supabaseでゴール、タスク、プランを保存する
        # NOTE: supabase-py に transaction がないので危険
        goal_response = supabase.table("goals").insert({"item_name": goal, "item_points": goal_points}).execute()
        goal_response_json = goal_response.json()
        goal_response_dict = json.loads(goal_response_json)["data"][0]

        print("created:", goal_response_dict)
        
        tasks_response = supabase.table("tasks").insert([{"task": task["task"], "point": task["point"], "goal_id": goal_response_dict["id"]} for task in tasks]).execute()
        tasks_response_json = tasks_response.json()
        tasks_response_dict = json.loads(tasks_response_json)["data"]

        print("created:", tasks_response_dict)

        tasks_ids_response = supabase.table("tasks_ids").insert([{"tasks_ids": [task["id"] for task in tasks_response_dict]}]).execute()
        tasks_ids_response_json = tasks_ids_response.json()
        tasks_ids_response_dict = json.loads(tasks_ids_response_json)["data"][0]

        plans = generate_daily_plans_tmp(goal=goal_response_dict, tasks=tasks_response_dict)
        # NOTE: flatmap的なこと
        plans_processed = []
        for plan in plans:
            for task in plan["plans_today"]:
                plans_processed.append({"day": plan["day"], "task_id": task["id"]})
        plans_response = supabase.table("plans").insert(plans_processed).execute()
        plans_response_json = plans_response.json()
        plans_response_dict = json.loads(plans_response_json)["data"]

        print("created:", plans_response_dict)

        plans_ids_response = supabase.table("plans_ids").insert([{"plans_ids": [plan["id"] for plan in plans_response_dict]}]).execute()
        plans_ids_response_json = plans_ids_response.json()
        plans_ids_response_dict = json.loads(plans_ids_response_json)["data"][0]

        # 生成したプランを含むレスポンスを返す
        return jsonify({"plans": plans, "plans_ids_id": plans_ids_response_dict["id"], "tasks_ids_id": tasks_ids_response_dict["id"]}), 200

    except Exception as e:
        # 例外が発生した場合はエラーメッセージを返す
        return jsonify({"error": str(e)}), 500


def generate_daily_plans(goal, tasks, days=7):
    goal_id = int(goal["id"])
    task_ids = [int(task["id"]) for task in tasks]

    # 毎日スケジュール
    daily_plans = []

    # 毎日、少なくとも一つのTODO
    for day in range(1, days + 1):
        task_id = random.choice(task_ids)
        daily_plans.append({"goal_id": goal_id, "day": day, "task_id": task_id})

    # 残りのTODOがある場合、ランダムに各日に分配
    remaining_tasks = len(task_ids) - days
    for _ in range(remaining_tasks):
        day = random.randint(1, days)
        task_id = random.choice(task_ids)
        daily_plans.append({"goal_id": goal_id, "day": day, "task_id": task_id})

    # 各TODOにポイント数
    for plan in daily_plans:
        plan['points'] = random.randint(1, 5)

    return daily_plans

def generate_daily_plans_tmp(goal, tasks):
    # FIXME: delete this
    return [
        {"day": 1, "plans_today": [random.choice(tasks)]},
        {"day": 2, "plans_today": [random.choice(tasks)]},
    ]


@app.route("/api/v1/plans/accept", methods=["POST"])
def accept_plan():
    """
    API Endpoint: /api/v1/plans/accept
    HTTP Method: POST

    Accept the suggested daily plans.

    Request:
    - Method: POST
    - Headers:
        Content-Type: application/json
    - Body (JSON):
        {
            "plans_ids_id": 1,
            "tasks_ids_id": 3,
        }

    Response:
    - Success (HTTP 200 OK):
        {
            "message": "Plan accepted"
        }
    - Bad Request (HTTP 400 Bad Request):
        {
            "error": "Invalid data format"
        }
    """

    try:
       # POSTリクエストのボディからJSONデータを取得
        request_data = request.get_json()

        # 必要なデータが揃っているか確認
        if "plans_ids_id" in request_data and "tasks_ids_id" in request_data:
            plans_ids_id = request_data["plans_ids_id"]
            tasks_ids_id = request_data["tasks_ids_id"]

            # goalsの最新のcreated_atを取得する
            goals_response = supabase.table("goals").select("*").order("created_at", desc=True).limit(1).execute()
            goals_response_json = goals_response.json()
            goals_response_dict = json.loads(goals_response_json)["data"][0]

            print("latest_goal:", goals_response_dict)
            
            supabase.table("goals").update({"status": 1}).eq("id", goals_response_dict["id"]).execute()

            # relationsを整備
            supabase.table("goals_relations").insert({"goal_id": goals_response_dict["id"], "plans_ids_id": plans_ids_id, "tasks_ids_id": tasks_ids_id}).execute()

            # レスポンスとしてメッセージを返す
            data = {"message": "Plan accepted"}
            return jsonify(data), 200
        else:
            # 必要なデータが見つからない場合はエラーメッセージを返す
            return jsonify({"error": "Invalid data format"}), 400

    except Exception as e:
        # 例外が発生した場合はエラーメッセージを返す
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/goals")
def check_goal():
    """
    API Endpoint: /api/v1/goals/check_goal
    HTTP Method: GET

    Check the current goal.

    Request:
    - Method: GET

    Response:
    - Success (HTTP 200 OK):
        {
            "goal": "computer",
            "goal_points": 100
        }
    """

    # ここでは固定のゴールと目標ポイントを返す例
    goal_response = supabase.table("goals").select("*").eq("status", 1).order("created_at", desc=True).limit(1).execute()
    goal_response_json = goal_response.json()
    goal_response_dict = json.loads(goal_response_json)["data"][0]

    print("latest_goal:", goal_response_dict)

    return jsonify({"goal": goal_response_dict["item_name"], "goal_points": goal_response_dict["item_points"]}), 200


@app.route("/api/v1/plans/check", methods=["GET"])
def check_progress():
    """
    API Endpoint: /api/v1/plans/check
    HTTP Method: GET

    Check if the daily plans are on track.

    Request:
    - Method: GET

    Response:
    - Success (HTTP 200 OK):
        If plans are on track
    - Need Adjustment (HTTP 200 OK):
        {
            "message": "Plans need adjustment",
            "adjusted_plans": [{"day": 1, "plans_today": [{"task": "cleaning", "point": 5}, ...]}, ...]
        }
    """

    # TODO: 単純に順調かどうかを真面目に決定
    is_on_track = random.choice([True, False])

    if is_on_track:
        # 順調な場合は200 OKを返す
        return jsonify({"message": "Plans are on track"}), 200
    else:
        # 順調でない場合は新たなプランを提案し直す
        adjusted_plans = suggest_adjusted_plans()
        return (
            jsonify(
                {"message": "Plans need adjustment", "adjusted_plans": adjusted_plans}
            ),
            200,
        )


def suggest_adjusted_plans():
    # 新たなプラン生成のロジックを追加する
    # ここでは単にランダムにプランを生成する例
    num_days = random.randint(1, 7)
    adjusted_plans = [
        {"day": day, "plans_today": [{"task": "cleaning", "point": 5}]}
        for day in range(1, num_days + 1)
    ]
    return adjusted_plans


@app.route("/api/v1/plans/today", methods=["POST"])
def get_today_plans():
    """
    API Endpoint: /api/v1/plans/today
    HTTP Method: POST

    Get plans for the specified day.

    Request:
    - Method: POST
    - Headers:
        Content-Type: application/json
    - Body (JSON):
        {
            "day": 1
        }

    Response:
    - Success (HTTP 200 OK):
        {
            "day": 1,
            "plans_today": [
                {"task": "cleaning", "point": 5}
            ]
        }
    - Bad Request (HTTP 400 Bad Request):
        {
            "error": "Invalid data format"
        }
    """

    try:
        # POSTリクエストのボディからJSONデータを取得
        request_data = request.get_json()

        # 必要なデータが揃っているか確認
        if "day" in request_data:
            day = request_data["day"]

            # TODO: データベースから指定された日のプランを取得するロジックを追加
            # goalsの最新のcreated_atを取得する
            goals_response = supabase.table("goals").select("*").order("created_at", desc=True).limit(1).execute()
            goals_response_json = goals_response.json()
            goals_response_dict = json.loads(goals_response_json)["data"][0]

            print("latest_goal:", goals_response_dict)

            plans_ids_id_response = supabase.table("goals_relations").select("plans_ids_id").eq("goal_id", goals_response_dict["id"]).order("created_at", desc=True).limit(1).execute()
            plans_ids_id_response_json = plans_ids_id_response.json()
            plans_ids_id_response_dict = json.loads(plans_ids_id_response_json)["data"][0]

            print("plans_ids_id:", plans_ids_id_response_dict)

            plans_ids_response = supabase.table("plans_ids").select("plans_ids").eq("id", plans_ids_id_response_dict["plans_ids_id"]).execute()
            plans_ids_response_json = plans_ids_response.json()
            plans_ids_response_dict = json.loads(plans_ids_response_json)["data"][0]

            print("plans_ids:", plans_ids_response_dict)

            plans_today_response = supabase.table("plans").select("*").in_("id", plans_ids_response_dict["plans_ids"]).eq("day", day).execute()
            plans_today_response_json = plans_today_response.json()
            plans_today_response_dict = json.loads(plans_today_response_json)["data"]

            print("plans_today:", plans_today_response_dict)

            plans_today = []
            for plan in plans_today_response_dict:
                task_response = supabase.table("tasks").select("*").eq("id", plan["task_id"]).execute()
                task_response_json = task_response.json()
                task_response_dict = json.loads(task_response_json)["data"][0]
                plans_today.append({"task": task_response_dict["task"], "point": task_response_dict["point"]})
            
            print("plans_today:", plans_today)

            return jsonify({"day": day, "plans_today": plans_today}), 200
        else:
            # 必要なデータが見つからない場合はエラーメッセージを返す
            return jsonify({"error": "Invalid data format"}), 400

    except Exception as e:
        # 例外が発生した場合はエラーメッセージを返す
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/submit", methods=["POST"])
def submit():
    """
    API Endpoint: /api/v1/submit
    HTTP Method: POST

    Submit daily tasks data.

    Request:
    - Method: POST
    - Headers:
        Content-Type: application/json
    - Body (JSON):
        {
            day: 1,
            total_points: 10,
        }

    Response:
    - Success (HTTP 200 OK):
        {
            "message": "Data received successfully"
        }
    - Bad Request (HTTP 400 Bad Request):
        {
            "error": "Invalid data format"
        }
    - Internal Server Error (HTTP 500 Internal Server Error):
        {
            "error": "Unexpected error occurred"
        }
    """
    try:
        # POSTリクエストのボディからJSONデータを取得
        json_data = request.get_json()

        if "day" in json_data and "total_points" in json_data:
            day = json_data["day"]
            total_points = json_data["total_points"]

            # goalsの最新のcreated_atを取得する
            goals_response = supabase.table("goals").select("*").order("created_at", desc=True).limit(1).execute()
            goals_response_json = goals_response.json()
            goals_response_dict = json.loads(goals_response_json)["data"][0]

            print("latest_goal:", goals_response_dict)

            supabase.table("progress").insert({"day": day, "total_points": total_points, "goal_id": goals_response_dict["id"]}).execute()

            # レスポンスとしてメッセージを返す
            return jsonify({"message": "Data received successfully"}), 200

        else:
            # 必要なデータが見つからない場合はエラーメッセージを返す
            return jsonify({"error": "Invalid data format"}), 400

    except Exception as e:
        # 例外が発生した場合はエラーメッセージを返す
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/points")
def get_points():
    """
    API Endpoint: /api/v1/points
    HTTP Method: GET

    Get the user's points.

    Request:
    - Method: GET

    Response:
    - Success (HTTP 200 OK):
        {
            "points": 88
        }
    """
    try:
        # goalsの最新のcreated_atを取得する
        goals_response = supabase.table("goals").select("*").order("created_at", desc=True).limit(1).execute()
        goals_response_json = goals_response.json()
        goals_response_dict = json.loads(goals_response_json)["data"][0]

        print("latest_goal:", goals_response_dict)

        progress_response = supabase.table("progress").select("*").eq("goal_id", goals_response_dict["id"]).execute()
        progress_response_json = progress_response.json()
        progress_response_dict = json.loads(progress_response_json)["data"]

        print("latest_progress:", progress_response_dict)

        total_points = 0
        for progress in progress_response_dict:
            total_points += progress["total_points"]

        return jsonify({"points": total_points}), 200
    
    except Exception as e:
        # 例外が発生した場合はエラーメッセージを返す
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
