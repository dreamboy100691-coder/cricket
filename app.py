from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import json
import os
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cricket-counter-secret-key-2024')
CORS(app)

# In-memory storage (replace with database in production)
matches = {}

class CricketMatch:
    def __init__(self, match_id):
        self.match_id = match_id
        self.scoreboard = [{"extras": 0, "balls": []}]  # Over 1 initialized
        self.current_over = 1
        self.current_ball = 1
        self.is_no_ball_pending = False
        self.target_mode = False
        self.target_runs = 0
        self.target_overs = 0
        self.edit_history = []
        self.created_at = datetime.now().isoformat()
        self.team_name = "Team A"
        self.opponent_name = "Team B"
        
    def to_dict(self):
        return {
            "match_id": self.match_id,
            "scoreboard": self.scoreboard,
            "current_over": self.current_over,
            "current_ball": self.current_ball,
            "is_no_ball_pending": self.is_no_ball_pending,
            "target_mode": self.target_mode,
            "target_runs": self.target_runs,
            "target_overs": self.target_overs,
            "total_runs": self.get_total_runs(),
            "total_wickets": self.get_total_wickets(),
            "overs_display": self.get_overs_display(),
            "edit_history": self.edit_history[-10:],
            "team_name": self.team_name,
            "opponent_name": self.opponent_name,
            "created_at": self.created_at
        }
    
    def get_total_runs(self):
        total = 0
        for over in self.scoreboard:
            total += over["extras"]
            for ball in over["balls"]:
                if isinstance(ball, (int, float)):
                    total += ball
        return total
    
    def get_total_wickets(self):
        wickets = 0
        for over in self.scoreboard:
            wickets += over["balls"].count("W")
        return wickets
    
    def get_overs_display(self):
        total_balls = (self.current_over - 1) * 6 + (self.current_ball - 1)
        overs = total_balls // 6
        balls = total_balls % 6
        return f"{overs}.{balls}"
    
    def record_ball(self, action):
        if self.current_ball > 6:
            return {"success": False, "message": "Over complete"}
        
        over_idx = self.current_over - 1
        if over_idx >= len(self.scoreboard):
            self.scoreboard.append({"extras": 0, "balls": []})
        
        over = self.scoreboard[over_idx]
        
        if action == "wide":
            over["extras"] += 1
            return {"success": True, "action": "wide"}
        
        if action == "noball":
            self.is_no_ball_pending = True
            over["extras"] += 1
            return {"success": True, "action": "noball"}
        
        # Regular balls
        ball_value = action
        if action == "dot":
            ball_value = "D"
        elif action == "wicket":
            ball_value = "W"
        else:
            ball_value = int(action)
        
        over["balls"].append(ball_value)
        
        if self.is_no_ball_pending:
            self.is_no_ball_pending = False
        else:
            self.current_ball += 1
        
        # Check over completion
        if self.current_ball > 6:
            self.current_ball = 1
            self.current_over += 1
            if self.current_over - 1 >= len(self.scoreboard):
                self.scoreboard.append({"extras": 0, "balls": []})
        
        return {"success": True, "action": action}
    
    def undo_last_ball(self):
        if not self.scoreboard:
            return {"success": False, "message": "Nothing to undo"}
        
        if self.current_over == 1 and self.current_ball == 1 and len(self.scoreboard[0]["balls"]) == 0:
            return {"success": False, "message": "Nothing to undo"}
        
        over_idx = self.current_over - 1
        
        if self.current_ball == 1:
            if over_idx > 0:
                over_idx -= 1
                self.current_over -= 1
                self.current_ball = 6
            else:
                return {"success": False, "message": "Nothing to undo"}
        else:
            self.current_ball -= 1
        
        over = self.scoreboard[over_idx]
        if over["balls"]:
            over["balls"].pop()
        elif over["extras"] > 0:
            over["extras"] = max(0, over["extras"] - 1)
        
        # Cleanup empty overs
        while len(self.scoreboard) > 1 and not self.scoreboard[-1]["balls"] and self.scoreboard[-1]["extras"] == 0:
            self.scoreboard.pop()
            if self.current_over > len(self.scoreboard):
                self.current_over = len(self.scoreboard)
                self.current_ball = 6
        
        self.is_no_ball_pending = False
        return {"success": True, "action": "undo"}
    
    def set_target(self, runs, overs):
        self.target_mode = True
        self.target_runs = int(runs)
        self.target_overs = int(overs)
        return {"success": True}
    
    def disable_target(self):
        self.target_mode = False
        return {"success": True}
    
    def edit_score(self, over_num, ball_num, new_value):
        idx = over_num - 1
        if idx < 0 or idx >= len(self.scoreboard):
            return {"success": False, "message": "Invalid over"}
        
        over = self.scoreboard[idx]
        ball_idx = ball_num - 1
        if ball_idx < 0 or ball_idx >= len(over["balls"]):
            return {"success": False, "message": "Ball not found"}
        
        old_val = over["balls"][ball_idx]
        
        # Parse new value
        if new_value.upper() == "W":
            new_val = "W"
        elif new_value.upper() == "D" or new_value == "0":
            new_val = "D"
        else:
            try:
                num = int(new_value)
                if 0 <= num <= 6:
                    new_val = num
                else:
                    return {"success": False, "message": "Invalid runs (0-6)"}
            except:
                return {"success": False, "message": "Invalid value"}
        
        over["balls"][ball_idx] = new_val
        self.edit_history.append(f"Over {over_num}.{ball_num}: {old_val} → {new_val}")
        return {"success": True}

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/match/new', methods=['POST'])
def new_match():
    match_id = str(uuid.uuid4())[:8]
    matches[match_id] = CricketMatch(match_id)
    session['match_id'] = match_id
    return jsonify({"success": True, "match_id": match_id, "match": matches[match_id].to_dict()})

@app.route('/api/match/<match_id>', methods=['GET'])
def get_match(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    return jsonify({"success": True, "match": matches[match_id].to_dict()})

@app.route('/api/match/<match_id>/action', methods=['POST'])
def record_action(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    data = request.json
    action = data.get('action')
    
    if not action:
        return jsonify({"success": False, "message": "No action provided"}), 400
    
    match = matches[match_id]
    
    if action in ['dot', '1', '2', '3', '4', '6', 'wicket', 'wide', 'noball']:
        result = match.record_ball(action)
    elif action == 'undo':
        result = match.undo_last_ball()
    else:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    result['match'] = match.to_dict()
    return jsonify(result)

@app.route('/api/match/<match_id>/target', methods=['POST'])
def set_target(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    data = request.json
    runs = data.get('runs')
    overs = data.get('overs')
    
    match = matches[match_id]
    
    if data.get('disable'):
        result = match.disable_target()
    elif runs and overs:
        result = match.set_target(runs, overs)
    else:
        return jsonify({"success": False, "message": "Missing parameters"}), 400
    
    result['match'] = match.to_dict()
    return jsonify(result)

@app.route('/api/match/<match_id>/edit', methods=['POST'])
def edit_score(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    data = request.json
    over = data.get('over')
    ball = data.get('ball')
    value = data.get('value')
    
    if not all([over, ball, value]):
        return jsonify({"success": False, "message": "Missing parameters"}), 400
    
    match = matches[match_id]
    result = match.edit_score(int(over), int(ball), str(value))
    result['match'] = match.to_dict()
    return jsonify(result)

@app.route('/api/match/<match_id>/reset', methods=['POST'])
def reset_match(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    matches[match_id] = CricketMatch(match_id)
    return jsonify({"success": True, "match": matches[match_id].to_dict()})

@app.route('/api/matches', methods=['GET'])
def list_matches():
    return jsonify({
        "success": True,
        "matches": [match.to_dict() for match in matches.values()]
    })

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_matches": len(matches)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))