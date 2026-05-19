from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cricket-scorer-pro-2024-secure-key')
CORS(app)

matches = {}

class Player:
    def __init__(self, pid, name, team):
        self.id = pid
        self.name = name
        self.team = team
        self.runs = 0
        self.balls = 0
        self.fours = 0
        self.sixes = 0
        self.out = False
        self.out_type = ""
        self.sr = 0.0
        self.is_playing = True

    def update_sr(self):
        if self.balls > 0:
            self.sr = round((self.runs / self.balls) * 100, 2)
        else:
            self.sr = 0.0

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'team': self.team,
            'runs': self.runs, 'balls': self.balls, 'fours': self.fours,
            'sixes': self.sixes, 'out': self.out, 'out_type': self.out_type,
            'sr': self.sr, 'is_playing': self.is_playing
        }

class Innings:
    def __init__(self, bat_team, bowl_team, total_overs, players_count=11):
        self.bat_team = bat_team
        self.bowl_team = bowl_team
        self.total_overs = total_overs
        self.players_count = players_count
        self.overs_data = [{"extras": 0, "balls": []}]
        self.cur_over = 1
        self.cur_ball = 1
        self.no_ball_pending = False
        self.runs = 0
        self.wickets = 0
        self.extras = 0
        self.wides = 0
        self.nb = 0
        self.byes = 0
        self.leg_byes = 0
        self.crr = 0.0
        self.rrr = 0.0
        self.target = None
        self.complete = False
        self.batsmen = [0, 1]
        self.next_bat = 2
        self.bowler_idx = 0
        self.max_wickets = players_count - 1

    def overs_str(self):
        balls = (self.cur_over - 1) * 6 + (self.cur_ball - 1)
        return f"{balls // 6}.{balls % 6}"

    def calc_crr(self):
        balls = (self.cur_over - 1) * 6 + (self.cur_ball - 1)
        if balls == 0:
            return 0.0
        return round(self.runs / (balls / 6), 2)

    def to_dict(self):
        return {
            'bat_team': self.bat_team,
            'bowl_team': self.bowl_team,
            'total_overs': self.total_overs,
            'players_count': self.players_count,
            'overs_data': self.overs_data,
            'cur_over': self.cur_over,
            'cur_ball': self.cur_ball,
            'no_ball_pending': self.no_ball_pending,
            'runs': self.runs,
            'wickets': self.wickets,
            'extras': self.extras,
            'wides': self.wides,
            'nb': self.nb,
            'byes': self.byes,
            'leg_byes': self.leg_byes,
            'crr': self.crr,
            'rrr': self.rrr,
            'target': self.target,
            'complete': self.complete,
            'batsmen': self.batsmen,
            'next_bat': self.next_bat,
            'bowler_idx': self.bowler_idx,
            'max_wickets': self.max_wickets,
            'overs_str': self.overs_str()
        }

class Match:
    def __init__(self, mid, t1, t2, overs, mtype, players_count=11):
        self.id = mid
        self.t1 = t1
        self.t2 = t2
        self.overs = overs
        self.mtype = mtype
        self.players_count = players_count
        self.status = "1st_innings"
        self.created = datetime.now().isoformat()
        
        # Create players based on count
        self.t1_players = [Player(f"t1p{i}", f"Player {i}", t1) for i in range(1, players_count + 1)]
        self.t2_players = [Player(f"t2p{i}", f"Player {i}", t2) for i in range(1, players_count + 1)]
        
        # Mark extra players as not playing if count > 11
        for i in range(11, len(self.t1_players)):
            self.t1_players[i].is_playing = False
        for i in range(11, len(self.t2_players)):
            self.t2_players[i].is_playing = False
        
        # Create innings
        self.innings = [Innings(t1, t2, overs, players_count)]
        self.cur_inn = 0

    def get_inn(self):
        if self.cur_inn < len(self.innings):
            return self.innings[self.cur_inn]
        return None

    def get_bat_players(self):
        inn = self.get_inn()
        if not inn:
            return []
        return self.t1_players if inn.bat_team == self.t1 else self.t2_players

    def get_playing_players(self, team):
        players = self.t1_players if team == self.t1 else self.t2_players
        return [p for p in players if p.is_playing][:self.players_count]

    def record_ball(self, action):
        inn = self.get_inn()
        if not inn:
            return {"success": False, "message": "No innings"}
        if inn.complete:
            return {"success": False, "message": "Innings complete"}
        if inn.cur_ball > 6:
            return {"success": False, "message": "Over complete"}

        # Ensure over exists
        while len(inn.overs_data) < inn.cur_over:
            inn.overs_data.append({"extras": 0, "balls": []})
        
        over = inn.overs_data[inn.cur_over - 1]
        bat_players = self.get_bat_players()
        playing_players = self.get_playing_players(inn.bat_team)

        # Wide ball
        if action == "wide":
            over["extras"] += 1
            inn.extras += 1
            inn.wides += 1
            inn.runs += 1
            inn.crr = inn.calc_crr()
            self._check_complete()
            return {"success": True, "action": "wide", "match": self.to_dict()}

        # No ball
        if action == "noball":
            inn.no_ball_pending = True
            over["extras"] += 1
            inn.extras += 1
            inn.nb += 1
            inn.runs += 1
            inn.crr = inn.calc_crr()
            self._check_complete()
            return {"success": True, "action": "noball", "match": self.to_dict()}

        # Regular deliveries
        striker_idx = inn.batsmen[0]
        
        if action == "dot":
            over["balls"].append("D")
            if striker_idx < len(bat_players):
                bat_players[striker_idx].balls += 1
                bat_players[striker_idx].update_sr()
                
        elif action == "wicket":
            over["balls"].append("W")
            inn.wickets += 1
            if striker_idx < len(bat_players):
                bat_players[striker_idx].balls += 1
                bat_players[striker_idx].out = True
                bat_players[striker_idx].out_type = "Out"
                bat_players[striker_idx].update_sr()
            
            # Get next batsman from playing players
            if inn.next_bat < len(playing_players):
                inn.batsmen[0] = inn.next_bat
                inn.next_bat += 1
            elif inn.wickets >= inn.max_wickets:
                inn.complete = True
                
        else:
            # Runs scored
            runs = int(action)
            over["balls"].append(runs)
            inn.runs += runs
            
            if striker_idx < len(bat_players):
                bat_players[striker_idx].runs += runs
                bat_players[striker_idx].balls += 1
                if runs == 4:
                    bat_players[striker_idx].fours += 1
                elif runs == 6:
                    bat_players[striker_idx].sixes += 1
                bat_players[striker_idx].update_sr()
            
            # Rotate strike for odd runs
            if runs % 2 == 1:
                inn.batsmen[0], inn.batsmen[1] = inn.batsmen[1], inn.batsmen[0]

        # Update ball count
        if inn.no_ball_pending:
            inn.no_ball_pending = False
        else:
            inn.cur_ball += 1

        # Over complete
        if inn.cur_ball > 6:
            inn.cur_ball = 1
            inn.cur_over += 1
            # Rotate strike at over end
            inn.batsmen[0], inn.batsmen[1] = inn.batsmen[1], inn.batsmen[0]
            # Initialize next over
            if len(inn.overs_data) < inn.cur_over:
                inn.overs_data.append({"extras": 0, "balls": []})

        # Check innings complete
        self._check_complete()
        inn.crr = inn.calc_crr()
        self._update_rrr()

        # Auto-start second innings
        if inn.complete and self.cur_inn == 0 and len(self.innings) == 1:
            self.start_second_innings()

        return {"success": True, "action": action, "match": self.to_dict()}

    def _check_complete(self):
        inn = self.get_inn()
        if not inn:
            return
        
        # Check wickets
        if inn.wickets >= inn.max_wickets:
            inn.complete = True
            return
        
        # Check overs
        total_balls = (inn.cur_over - 1) * 6 + (inn.cur_ball - 1)
        if total_balls >= inn.total_overs * 6:
            inn.complete = True
            return
        
        # Check target chased
        if self.cur_inn == 1 and inn.target and inn.runs >= inn.target:
            inn.complete = True

    def undo_ball(self):
        inn = self.get_inn()
        if not inn:
            return {"success": False, "message": "No innings"}

        # Nothing to undo
        if inn.cur_over == 1 and inn.cur_ball == 1:
            if len(inn.overs_data) > 0 and len(inn.overs_data[0]["balls"]) == 0 and inn.overs_data[0]["extras"] == 0:
                return {"success": False, "message": "Nothing to undo"}

        # Go back one ball
        if inn.cur_ball == 1:
            if inn.cur_over > 1:
                inn.cur_over -= 1
                inn.cur_ball = 6
            else:
                return {"success": False, "message": "Nothing to undo"}
        else:
            inn.cur_ball -= 1

        if inn.cur_over > len(inn.overs_data):
            return {"success": False, "message": "Cannot undo"}

        over = inn.overs_data[inn.cur_over - 1]
        bat_players = self.get_bat_players()

        if len(over["balls"]) > 0:
            last = over["balls"].pop()
            
            if isinstance(last, int):
                inn.runs -= last
                striker_idx = inn.batsmen[0]
                if striker_idx < len(bat_players):
                    bat_players[striker_idx].runs = max(0, bat_players[striker_idx].runs - last)
                    bat_players[striker_idx].balls = max(0, bat_players[striker_idx].balls - 1)
                    if last == 4:
                        bat_players[striker_idx].fours = max(0, bat_players[striker_idx].fours - 1)
                    elif last == 6:
                        bat_players[striker_idx].sixes = max(0, bat_players[striker_idx].sixes - 1)
                    bat_players[striker_idx].update_sr()
                    # Reverse strike rotation
                    if last % 2 == 1:
                        inn.batsmen[0], inn.batsmen[1] = inn.batsmen[1], inn.batsmen[0]
                        
            elif last == "W":
                inn.wickets = max(0, inn.wickets - 1)
                striker_idx = inn.batsmen[0]
                if striker_idx < len(bat_players):
                    bat_players[striker_idx].out = False
                    bat_players[striker_idx].out_type = ""
                    bat_players[striker_idx].balls = max(0, bat_players[striker_idx].balls - 1)
                    bat_players[striker_idx].update_sr()
                inn.next_bat = max(2, inn.next_bat - 1)
                
            elif last == "D":
                striker_idx = inn.batsmen[0]
                if striker_idx < len(bat_players):
                    bat_players[striker_idx].balls = max(0, bat_players[striker_idx].balls - 1)
                    bat_players[striker_idx].update_sr()
        else:
            # Undo extras
            if over["extras"] > 0:
                over["extras"] -= 1
                inn.extras = max(0, inn.extras - 1)
                inn.runs = max(0, inn.runs - 1)
                # Determine which extra
                if inn.wides > 0:
                    inn.wides = max(0, inn.wides - 1)
                elif inn.nb > 0:
                    inn.nb = max(0, inn.nb - 1)

        inn.no_ball_pending = False
        inn.complete = False
        inn.crr = inn.calc_crr()
        self._update_rrr()

        # Clean empty overs
        while len(inn.overs_data) > 1 and len(inn.overs_data[-1]["balls"]) == 0 and inn.overs_data[-1]["extras"] == 0:
            inn.overs_data.pop()
            if inn.cur_over > len(inn.overs_data):
                inn.cur_over = len(inn.overs_data)

        return {"success": True, "action": "undo", "match": self.to_dict()}

    def start_second_innings(self):
        target = self.innings[0].runs + 1
        inn2 = Innings(self.t2, self.t1, self.overs, self.players_count)
        inn2.target = target
        inn2.rrr = round(target / self.overs, 2)
        self.innings.append(inn2)
        self.cur_inn = 1
        self.status = "2nd_innings"

    def switch_innings(self):
        if len(self.innings) > 1:
            self.cur_inn = 1
            self.status = "2nd_innings"
            self._update_rrr()
            return True
        return False

    def _update_rrr(self):
        if self.cur_inn == 1 and len(self.innings) > 1:
            inn = self.innings[1]
            if self.innings[0].complete:
                target = self.innings[0].runs + 1
                inn.target = target
                runs_needed = target - inn.runs
                balls_done = (inn.cur_over - 1) * 6 + (inn.cur_ball - 1)
                balls_left = (self.overs * 6) - balls_done
                if balls_left > 0 and runs_needed > 0:
                    inn.rrr = round(runs_needed / (balls_left / 6), 2)
                else:
                    inn.rrr = 0.0

    def update_players(self, team, updates):
        players = self.t1_players if team == "t1" else self.t2_players
        for u in updates:
            for p in players:
                if p.id == u['id']:
                    if 'name' in u:
                        p.name = u['name']
                    if 'is_playing' in u:
                        p.is_playing = u['is_playing']
                    break
        return True

    def to_dict(self):
        inn = self.get_inn()
        bat_players = self.get_bat_players()
        return {
            'id': self.id,
            't1': self.t1, 't2': self.t2,
            'overs': self.overs, 'mtype': self.mtype,
            'players_count': self.players_count,
            'status': self.status,
            'cur_inn': self.cur_inn,
            'innings': [i.to_dict() for i in self.innings],
            't1_players': [p.to_dict() for p in self.t1_players],
            't2_players': [p.to_dict() for p in self.t2_players],
            'bat_players': [p.to_dict() for p in bat_players],
            'current_innings': inn.to_dict() if inn else None,
            'created': self.created
        }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "matches": len(matches), "timestamp": datetime.now().isoformat()})

@app.route('/api/match/new', methods=['POST'])
def new_match():
    data = request.json or {}
    mid = str(uuid.uuid4())[:8]
    t1 = data.get('t1', 'Team A')
    t2 = data.get('t2', 'Team B')
    overs = int(data.get('overs', 20))
    mtype = data.get('mtype', 'T20')
    players_count = int(data.get('players_count', 11))
    
    # Validate players count
    if players_count < 2 or players_count > 15:
        players_count = 11
    
    match = Match(mid, t1, t2, overs, mtype, players_count)
    matches[mid] = match
    return jsonify({"success": True, "match": match.to_dict()})

@app.route('/api/match/<mid>')
def get_match(mid):
    if mid not in matches:
        return jsonify({"success": False, "message": "Match not found"}), 404
    return jsonify({"success": True, "match": matches[mid].to_dict()})

@app.route('/api/match/<mid>/action', methods=['POST'])
def action(mid):
    if mid not in matches:
        return jsonify({"success": False}), 404
    
    data = request.json
    act = data.get('action')
    match = matches[mid]
    
    if act == 'undo':
        res = match.undo_ball()
    elif act == 'switch':
        if match.switch_innings():
            res = {"success": True, "match": match.to_dict()}
        else:
            res = {"success": False, "message": "Cannot switch innings"}
    elif act in ['dot','1','2','3','4','6','wicket','wide','noball']:
        res = match.record_ball(act)
    else:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    return jsonify(res)

@app.route('/api/match/<mid>/players', methods=['PUT'])
def update_players(mid):
    if mid not in matches:
        return jsonify({"success": False}), 404
    
    data = request.json
    match = matches[mid]
    
    if data.get('t1_players'):
        match.update_players('t1', data['t1_players'])
    if data.get('t2_players'):
        match.update_players('t2', data['t2_players'])
    
    return jsonify({"success": True, "match": match.to_dict()})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
