from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import json
import os
from datetime import datetime
import uuid
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cricket-pro-scorer-2024-secret')
CORS(app)

# In-memory storage
matches = {}

class Player:
    def __init__(self, player_id, name, is_batsman=True):
        self.id = player_id
        self.name = name
        self.runs = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.is_out = False
        self.out_type = None
        self.bowler_name = None
        self.fielder_name = None
        self.strike_rate = 0.0
        
    def update_strike_rate(self):
        if self.balls_faced > 0:
            self.strike_rate = round((self.runs / self.balls_faced) * 100, 2)
        else:
            self.strike_rate = 0.0
            
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'runs': self.runs,
            'balls_faced': self.balls_faced,
            'fours': self.fours,
            'sixes': self.sixes,
            'is_out': self.is_out,
            'out_type': self.out_type,
            'strike_rate': self.strike_rate
        }

class CricketMatch:
    def __init__(self, match_id):
        self.match_id = match_id
        self.innings = []  # List of innings
        self.current_innings = 0  # 0 = first innings, 1 = second innings
        self.total_overs = 20  # Default T20
        self.match_type = "T20"  # T20, ODI, Test
        self.team1_name = "Team A"
        self.team2_name = "Team B"
        self.toss_winner = None
        self.batting_first = None
        self.created_at = datetime.now().isoformat()
        self.match_status = "not_started"  # not_started, in_progress, innings_break, completed
        
        # Initialize players with default names
        self.team1_players = [Player(f"t1_p{i}", f"Player {i}") for i in range(1, 12)]
        self.team2_players = [Player(f"t2_p{i}", f"Player {i}") for i in range(1, 12)]
        
        # Current batting team players
        self.current_batsmen = [None, None]  # [striker, non-striker]
        self.current_bowler = None
        self.batsmen_index = 0
        
        # Initialize first innings
        self.innings.append({
            'batting_team': self.team1_name,
            'bowling_team': self.team2_name,
            'scoreboard': [{"extras": 0, "balls": []}],
            'current_over': 1,
            'current_ball': 1,
            'is_no_ball_pending': False,
            'total_runs': 0,
            'total_wickets': 0,
            'overs_display': "0.0",
            'run_rate': 0.0,
            'required_run_rate': 0.0,
            'target': None,
            'extras_total': 0,
            'wide_count': 0,
            'no_ball_count': 0,
            'bye_runs': 0,
            'leg_bye_runs': 0
        })
        
        # Auto-set opening batsmen
        self.current_batsmen = [0, 1]  # Index of players
        self.current_bowler = 0  # Index of bowler from bowling team
        
    def get_current_innings(self):
        if self.current_innings < len(self.innings):
            return self.innings[self.current_innings]
        return None
    
    def get_batting_team_players(self):
        if self.current_innings == 0:
            return self.team1_players if self.innings[0]['batting_team'] == self.team1_name else self.team2_players
        else:
            return self.team2_players if self.innings[1]['batting_team'] == self.team2_name else self.team1_players
    
    def get_total_runs(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return 0
        total = 0
        for over in innings_data['scoreboard']:
            total += over["extras"]
            for ball in over["balls"]:
                if isinstance(ball, (int, float)):
                    total += ball
        return total
    
    def get_total_wickets(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return 0
        wickets = 0
        for over in innings_data['scoreboard']:
            wickets += over["balls"].count("W")
        return wickets
    
    def get_overs_display(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return "0.0"
        total_balls = (innings_data['current_over'] - 1) * 6 + (innings_data['current_ball'] - 1)
        overs = total_balls // 6
        balls = total_balls % 6
        return f"{overs}.{balls}"
    
    def calculate_run_rate(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return 0.0
        total_balls = (innings_data['current_over'] - 1) * 6 + (innings_data['current_ball'] - 1)
        if total_balls == 0:
            return 0.0
        overs_bowled = total_balls / 6
        return round(self.get_total_runs() / overs_bowled, 2) if overs_bowled > 0 else 0.0
    
    def calculate_required_run_rate(self):
        if self.current_innings == 0:
            return 0.0
        if len(self.innings) < 2:
            return 0.0
        
        target = self.innings[0]['total_runs'] + 1
        current_runs = self.get_total_runs()
        runs_needed = target - current_runs
        
        total_balls = (self.innings[1]['current_over'] - 1) * 6 + self.innings[1]['current_ball'] - 1
        balls_remaining = (self.total_overs * 6) - total_balls
        
        if balls_remaining <= 0:
            return 0.0
        
        overs_remaining = balls_remaining / 6
        return round(runs_needed / overs_remaining, 2) if overs_remaining > 0 else 0.0
    
    def record_ball(self, action, runs=0):
        innings_data = self.get_current_innings()
        if not innings_data:
            return {"success": False, "message": "No active innings"}
        
        if innings_data['current_ball'] > 6:
            return {"success": False, "message": "Over complete"}
        
        over_idx = innings_data['current_over'] - 1
        if over_idx >= len(innings_data['scoreboard']):
            innings_data['scoreboard'].append({"extras": 0, "balls": []})
        
        over = innings_data['scoreboard'][over_idx]
        batting_players = self.get_batting_team_players()
        
        # Handle different actions
        if action == "wide":
            over["extras"] += 1
            innings_data['extras_total'] += 1
            innings_data['wide_count'] += 1
            # Update batsman doesn't face the ball
        elif action == "noball":
            innings_data['is_no_ball_pending'] = True
            over["extras"] += 1
            innings_data['extras_total'] += 1
            innings_data['no_ball_count'] += 1
        else:
            ball_value = action
            if action == "dot":
                ball_value = "D"
            elif action == "wicket":
                ball_value = "W"
                # Update wicket count
                striker_idx = self.current_batsmen[0]
                if striker_idx is not None and striker_idx < len(batting_players):
                    batting_players[striker_idx].is_out = True
                    batting_players[striker_idx].out_type = "Bowled"
                    batting_players[striker_idx].update_strike_rate()
                
                # Get next batsman
                self.batsmen_index += 1
                next_batsman = self.batsmen_index
                if next_batsman < len(batting_players):
                    self.current_batsmen[0] = next_batsman
                
                # Check if all out
                if self.get_total_wickets() >= 10:
                    self.end_innings()
                    
            else:
                runs = int(action)
                # Update striker's runs
                striker_idx = self.current_batsmen[0]
                if striker_idx is not None and striker_idx < len(batting_players):
                    batting_players[striker_idx].runs += runs
                    batting_players[striker_idx].balls_faced += 1
                    if runs == 4:
                        batting_players[striker_idx].fours += 1
                    elif runs == 6:
                        batting_players[striker_idx].sixes += 1
                    batting_players[striker_idx].update_strike_rate()
                
                # Rotate strike for odd runs
                if runs % 2 == 1:
                    self.current_batsmen[0], self.current_batsmen[1] = self.current_batsmen[1], self.current_batsmen[0]
                
                ball_value = runs
            
            over["balls"].append(ball_value)
            
            if innings_data['is_no_ball_pending']:
                innings_data['is_no_ball_pending'] = False
            else:
                innings_data['current_ball'] += 1
            
            # Check over completion
            if innings_data['current_ball'] > 6:
                innings_data['current_ball'] = 1
                innings_data['current_over'] += 1
                if innings_data['current_over'] - 1 >= len(innings_data['scoreboard']):
                    innings_data['scoreboard'].append({"extras": 0, "balls": []})
                
                # Rotate strike at over end
                self.current_batsmen[0], self.current_batsmen[1] = self.current_batsmen[1], self.current_batsmen[0]
        
        # Update innings totals
        innings_data['total_runs'] = self.get_total_runs()
        innings_data['total_wickets'] = self.get_total_wickets()
        innings_data['overs_display'] = self.get_overs_display()
        innings_data['run_rate'] = self.calculate_run_rate()
        
        if self.current_innings == 1:
            innings_data['required_run_rate'] = self.calculate_required_run_rate()
            innings_data['target'] = self.innings[0]['total_runs'] + 1
        
        # Check if innings is complete
        if self.check_innings_complete():
            self.end_innings()
        
        return {"success": True, "action": action}
    
    def check_innings_complete(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return False
        
        # All out
        if self.get_total_wickets() >= 10:
            return True
        
        # Overs complete
        total_balls = (innings_data['current_over'] - 1) * 6 + (innings_data['current_ball'] - 1)
        if total_balls >= self.total_overs * 6:
            return True
        
        # Target chased (second innings)
        if self.current_innings == 1 and len(self.innings) >= 2:
            if self.get_total_runs() > self.innings[0]['total_runs']:
                return True
        
        return False
    
    def end_innings(self):
        innings_data = self.get_current_innings()
        if not innings_data:
            return
        
        if self.current_innings == 0:
            # Start second innings
            self.match_status = "innings_break"
            self.current_innings = 1
            
            # Create second innings
            self.innings.append({
                'batting_team': self.team2_name,
                'bowling_team': self.team1_name,
                'scoreboard': [{"extras": 0, "balls": []}],
                'current_over': 1,
                'current_ball': 1,
                'is_no_ball_pending': False,
                'total_runs': 0,
                'total_wickets': 0,
                'overs_display': "0.0",
                'run_rate': 0.0,
                'required_run_rate': self.calculate_required_run_rate(),
                'target': self.innings[0]['total_runs'] + 1,
                'extras_total': 0,
                'wide_count': 0,
                'no_ball_count': 0,
                'bye_runs': 0,
                'leg_bye_runs': 0
            })
            
            # Reset batsmen for second innings
            self.current_batsmen = [0, 1]
            self.batsmen_index = 1
            
        else:
            # Match complete
            self.match_status = "completed"
    
    def to_dict(self):
        batting_players = self.get_batting_team_players()
        return {
            'match_id': self.match_id,
            'team1_name': self.team1_name,
            'team2_name': self.team2_name,
            'match_type': self.match_type,
            'total_overs': self.total_overs,
            'match_status': self.match_status,
            'current_innings': self.current_innings,
            'innings': self.innings,
            'team1_players': [p.to_dict() for p in self.team1_players],
            'team2_players': [p.to_dict() for p in self.team2_players],
            'current_batsmen': self.current_batsmen,
            'batting_team_players': [p.to_dict() for p in batting_players],
            'created_at': self.created_at
        }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/match/new', methods=['POST'])
def new_match():
    data = request.json or {}
    match_id = str(uuid.uuid4())[:8]
    match = CricketMatch(match_id)
    
    # Customize match settings
    if data.get('team1_name'):
        match.team1_name = data['team1_name']
    if data.get('team2_name'):
        match.team2_name = data['team2_name']
    if data.get('total_overs'):
        match.total_overs = int(data['total_overs'])
        match.match_type = "Custom"
    if data.get('match_type'):
        match.match_type = data['match_type']
        if data['match_type'] == 'ODI':
            match.total_overs = 50
        elif data['match_type'] == 'T20':
            match.total_overs = 20
        elif data['match_type'] == 'Test':
            match.total_overs = 90
    
    # Update innings with correct team names
    match.innings[0]['batting_team'] = match.team1_name
    match.innings[0]['bowling_team'] = match.team2_name
    
    match.match_status = "in_progress"
    matches[match_id] = match
    session['match_id'] = match_id
    
    return jsonify({"success": True, "match_id": match_id, "match": match.to_dict()})

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
    runs = data.get('runs', 0)
    
    match = matches[match_id]
    
    valid_actions = ['dot', '1', '2', '3', '4', '6', 'wicket', 'wide', 'noball']
    if action not in valid_actions:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    result = match.record_ball(action, runs)
    result['match'] = match.to_dict()
    return jsonify(result)

@app.route('/api/match/<match_id>/players', methods=['PUT'])
def update_players(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    data = request.json
    match = matches[match_id]
    
    if data.get('team1_players'):
        for i, player_data in enumerate(data['team1_players']):
            if i < len(match.team1_players):
                match.team1_players[i].name = player_data.get('name', match.team1_players[i].name)
    
    if data.get('team2_players'):
        for i, player_data in enumerate(data['team2_players']):
            if i < len(match.team2_players):
                match.team2_players[i].name = player_data.get('name', match.team2_players[i].name)
    
    return jsonify({"success": True, "match": match.to_dict()})

@app.route('/api/match/<match_id>/settings', methods=['PUT'])
def update_settings(match_id):
    if match_id not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    
    data = request.json
    match = matches[match_id]
    
    if data.get('total_overs'):
        match.total_overs = int(data['total_overs'])
    if data.get('team1_name'):
        match.team1_name = data['team1_name']
    if data.get('team2_name'):
        match.team2_name = data['team2_name']
    
    return jsonify({"success": True, "match": match.to_dict()})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_matches": len(matches)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
