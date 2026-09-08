-- Pili Pili - Tabletop Simulator table script
--
-- Everything lives on the table: a chilli button in the middle that runs the
-- round, a +/- dibber in front of each seat for that player's bet, a mat where
-- you stack the tricks you win, and a tray your Pilis land in.
--
-- The button never has to work out who won a trick. Every trick holds exactly
-- one card per player, so tricks won = cards in your pile / number of players.
-- That keeps the missions that rewrite trick resolution (Upside Down and the
-- rest) entirely out of the script's business.

TAG_PLAY = "PILI:PLAY"
TAG_MISSION = "PILI:MISSION"
TAG_DIBBER = "PILI:DIBBER:"
TAG_TRICKS = "PILI:TRICKS:"
TAG_PILIS = "PILI:PILIS:"
TAG_MAT = "PILI:MAT:"
TAG_TRAY = "PILI:TRAY:"
TAG_BUTTON = "PILI:BUTTON"
TAG_DEALER = "PILI:DEALER"
TAG_MTOGGLE = "PILI:MTOGGLE"

-- POS_PLAY, POS_ASIDE, POS_MISSION, POS_REVEAL and POS_DISCARD are injected
-- above this line by build_save.py, from the same constants that place the
-- objects in the save. Do not redeclare them here or they will drift apart.

PILI_LIMIT = 6

GOLD = {0.91, 0.77, 0.36}
HOT = {1.0, 0.38, 0.32}
COOL = {0.55, 0.85, 0.65}

bids = {}          -- colour -> bet, nil until that player touches their dibber
dealt = 0          -- cards dealt each this round
busy = false       -- guard, the round sequence is asynchronous
missionsOn = false -- off by default - the rulebook's own suggested first game
                   -- skips missions entirely; flip the tile by the mission
                   -- deck to turn them on
seenIntro = false  -- whether the one-time "read the rulebook" hint has shown

-- ------------------------------------------------------------------ state --

function onSave()
    return JSON.encode({bids = bids, dealt = dealt, missionsOn = missionsOn,
                        seenIntro = seenIntro})
end

function onLoad(state)
    if state ~= nil and state ~= "" then
        local ok, s = pcall(function() return JSON.decode(state) end)
        if ok and s ~= nil then
            bids = s.bids or {}
            dealt = s.dealt or 0
            missionsOn = s.missionsOn or false
            seenIntro = s.seenIntro or false
        end
    end
    Wait.time(buildControls, 0.6)
    -- On-table messages are deliberately terse status pings now, not
    -- instructions - this is the one time the full explanation gets pointed
    -- at, rather than repeated on every deal/bet/round.
    if not seenIntro then
        Wait.time(function()
            seenIntro = true
            broadcastToAll("New here? The rulebook on the table opens on click.", GOLD)
        end, 2.0)
    end
end

-- ------------------------------------------------------------------ finding --

function tagged(tag, exact)
    local out = {}
    for _, o in ipairs(getAllObjects()) do
        local n = o.getGMNotes()
        if n ~= nil and n ~= "" then
            if (exact and n == tag) or (not exact and string.sub(n, 1, #tag) == tag) then
                table.insert(out, o)
            end
        end
    end
    return out
end

function one(tag)
    return tagged(tag, true)[1]
end

function seatOf(obj, prefix)
    return string.sub(obj.getGMNotes(), #prefix + 1)
end

function cardsTagged(tag)
    local out = {}
    for _, o in ipairs(getAllObjects()) do
        local t = o.type
        if (t == "Card" or t == "Deck") and o.getGMNotes() == tag then
            table.insert(out, o)
        end
    end
    return out
end

function countIn(o)
    if o.type == "Deck" then return #o.getObjects() end
    return 1
end

function biggest(tag)
    local best, n = nil, -1
    for _, o in ipairs(cardsTagged(tag)) do
        local c = countIn(o)
        if c > n then best, n = o, c end
    end
    return best
end

function seatedSet()
    local s = {}
    for _, c in ipairs(getSeatedPlayers()) do s[c] = true end
    return s
end

-- ------------------------------------------------------------------ controls --

function buildControls()
    buildDibberButtons()

    local b = one(TAG_BUTTON)
    if b ~= nil then
        b.clearButtons()
        b.createButton({
            click_function = "nextRound", function_owner = Global, label = "",
            position = {0, 0.3, 0}, width = 1500, height = 700,
            color = {0, 0, 0, 0},
            tooltip = "Score this round, reshuffle, new mission, deal",
        })
    end

    local mt = one(TAG_MTOGGLE)
    if mt ~= nil then
        mt.clearButtons()
        -- Smaller and lower than before: the baked "MISSIONS" title moved up
        -- near the tile's top edge (see art.py's plaque title_y), and this
        -- button used to be tall/centred enough to sit right on top of it,
        -- which is what made the title unreadable. Shrinking the button
        -- clears that regardless of which local axis actually maps to "up"
        -- on the image - safer than guessing the sign and nudging position.
        mt.createButton({
            click_function = "toggleMissions", function_owner = Global,
            label = missionsLabel(),
            position = {0, 0.3, 0.05}, width = 900, height = 220,
            font_size = 230, color = {0.12, 0.11, 0.09}, font_color = {1, 0.95, 0.8},
            tooltip = "Turn Mission cards on or off for future rounds",
        })
    end

end

function missionsLabel()
    if missionsOn then return "ON" end
    return "OFF"
end

function toggleMissions()
    missionsOn = not missionsOn
    Wait.frames(function()
        local mt = one(TAG_MTOGGLE)
        -- index 0, not 1: this tile creates exactly ONE button (no explicit
        -- index, so TTS numbers it 0 by creation order). The dibber's
        -- editButton uses index 1 correctly, because it creates three
        -- buttons in order (-, centre, +) and 1 is genuinely the centre one -
        -- that pattern got copied here without adjusting for there being
        -- only one button, which is what actually crashed this.
        if mt ~= nil then mt.editButton({index = 0, label = missionsLabel()}) end
    end, 1)
    if missionsOn then
        broadcastToAll("Missions: ON from next round.", GOLD)
    else
        broadcastToAll("Missions: OFF from next round.", GOLD)
    end
end

function bidLabel(colour)
    local b = bids[colour]
    if b == nil then return "" end
    return tostring(b)
end

-- ------------------------------------------------------------------ betting --
--
-- One numbered button per possible bet (0..dealt) plus a big persistent
-- display of the current pick - replaces an earlier +/- counter whose
-- current value was a small label easy to miss, on a tile with no visible
-- indication of what a fresh, blank centre even was.
--
-- Rebuilt every time `dealt` changes (a new deal can have a different card
-- count), since the number of buttons itself depends on it.

MAX_BID = 11  -- generous headroom above missions.json's current 2-7 range;
              -- bidPick0..bidPickMAX must exist as real functions below,
              -- since TTS click handlers take no custom argument - see those.

BTN_NORMAL = {0.55, 0.10, 0.09}
FONT_NORMAL = {1, 1, 1}
BTN_SELECTED = {0.80, 0.64, 0.20}
FONT_SELECTED = {0.12, 0.10, 0.06}
BTN_FORBIDDEN = {0.22, 0.20, 0.19}
FONT_FORBIDDEN = {0.50, 0.47, 0.45}

-- The seat/outward split below (see the two comments inline) is derived from
-- rotY=180, the facing shared by the four straight-edge seats. Red and Purple
-- use their own rotation (see SEATS in build_save.py) to face the felt
-- correctly, which was never checked against this same z-axis math - their
-- dibbers may not split seat-side/table-side as cleanly as the other four.
function buildDibberButtons()
    for _, d in ipairs(tagged(TAG_DIBBER, false)) do
        d.clearButtons()
        local colour = seatOf(d, TAG_DIBBER)

        -- index 0: the big display, meant to be read by everyone ELSE at
        -- the table - it faces outward, away from the seat (local +Z, which
        -- rotY=180 - the shared facing for every straight-edge seat - turns
        -- into world -Z, i.e. toward the table's own centre). Its own click
        -- just repeats the hint; betting itself only happens on the row
        -- below, which sits on the opposite (seat-facing) side so the
        -- player reaches for it naturally rather than across the display.
        d.createButton({
            click_function = "bidNudge", function_owner = Global,
            label = bidLabel(colour),
            position = {0, 0.3, 0.40}, width = 1000, height = 560,
            font_size = 440, color = {0.08, 0.07, 0.07}, font_color = {1, 0.95, 0.82},
            tooltip = colour .. "'s bet - tap a number below to set it",
        })

        local n = math.max(dealt, 0)
        if n > 0 then
            local step = 1.7 / n
            for k = 0, n do
                d.createButton({
                    click_function = "bidPick" .. k, function_owner = Global,
                    label = tostring(k),
                    position = {-0.85 + step * k, 0.3, -0.42}, width = 150, height = 210,
                    font_size = 120, color = BTN_NORMAL, font_color = FONT_NORMAL,
                    tooltip = colour .. ": bet " .. k,
                })
            end
        end
    end
    refreshForbidden()
end

function bidNudge(obj, player_colour)
    if dealt <= 0 then
        broadcastToColor("Nothing dealt yet - press the chilli.", player_colour, GOLD)
    else
        broadcastToColor("Tap a number below to set your bet.", player_colour, GOLD)
    end
end

-- Numbered click handlers. TTS's click_function callback is always
-- (object, player_colour, alt_click) - it carries no data of its own, so a
-- button whose action depends on a specific number needs its own uniquely
-- named function per number rather than one shared handler with an argument.
function bidPick0(obj, c) setBid(obj, c, 0) end
function bidPick1(obj, c) setBid(obj, c, 1) end
function bidPick2(obj, c) setBid(obj, c, 2) end
function bidPick3(obj, c) setBid(obj, c, 3) end
function bidPick4(obj, c) setBid(obj, c, 4) end
function bidPick5(obj, c) setBid(obj, c, 5) end
function bidPick6(obj, c) setBid(obj, c, 6) end
function bidPick7(obj, c) setBid(obj, c, 7) end
function bidPick8(obj, c) setBid(obj, c, 8) end
function bidPick9(obj, c) setBid(obj, c, 9) end
function bidPick10(obj, c) setBid(obj, c, 10) end
function bidPick11(obj, c) setBid(obj, c, 11) end

function setBid(obj, player_colour, want)
    local seat = seatOf(obj, TAG_DIBBER)
    local p = Player[player_colour]
    if player_colour ~= seat and not (p ~= nil and p.admin) then
        broadcastToColor("That is " .. seat .. "'s dibber, not yours.", player_colour, HOT)
        return
    end
    if dealt <= 0 or want > dealt then return end

    -- The bets must not total the cards dealt, and that binds whoever bets
    -- last. If everyone else has bet, this player is last, so refuse the one
    -- number that would make the totals match - refreshForbidden() already
    -- greys that button out, this is the backstop if it gets clicked anyway.
    local others, missing = 0, 0
    for c, _ in pairs(seatedSet()) do
        if c ~= seat then
            if bids[c] == nil then missing = missing + 1 else others = others + bids[c] end
        end
    end
    if missing == 0 and others + want == dealt then
        broadcastToAll(seat .. ": can't total " .. dealt .. " - pick another.", HOT)
        return
    end

    bids[seat] = want
    local d = one(TAG_DIBBER .. seat)
    if d ~= nil then d.editButton({index = 0, label = bidLabel(seat)}) end
    refreshForbidden()

    local total, unset = 0, 0
    for c, _ in pairs(seatedSet()) do
        if bids[c] == nil then unset = unset + 1 else total = total + bids[c] end
    end
    if unset == 0 then
        broadcastToAll("Bets in: " .. total .. "/" .. dealt .. ". Play!", GOLD)
    end
end

-- Recolours every seat's number row: gold on the seat's current pick, grey
-- on the one number that would illegally tie the total for whichever seat
-- is currently the sole one left to bet, plain red otherwise. Runs after
-- every bid change, since one player's pick can create or clear that
-- restriction for a different seat.
function refreshForbidden()
    local seated = seatedSet()
    for _, d in ipairs(tagged(TAG_DIBBER, false)) do
        local colour = seatOf(d, TAG_DIBBER)
        if seated[colour] then
            local n = math.max(dealt, 0)
            local forbidden = nil
            if bids[colour] == nil and n > 0 then
                local others, missing = 0, 0
                for c, _ in pairs(seated) do
                    if c ~= colour then
                        if bids[c] == nil then missing = missing + 1
                        else others = others + bids[c] end
                    end
                end
                if missing == 0 then
                    local f = dealt - others
                    if f >= 0 and f <= dealt then forbidden = f end
                end
            end
            local selected = bids[colour]
            -- buildDibberButtons() only creates the number row when n > 0 -
            -- editing button k+1 here when n == 0 would touch a button that
            -- was never created (only the display exists then), which is
            -- exactly what crashed on every fresh table load before a single
            -- "Next Round" press ever happened.
            for k = 0, n do
                if n == 0 then break end
                local col, fcol
                if forbidden == k then col, fcol = BTN_FORBIDDEN, FONT_FORBIDDEN
                elseif selected == k then col, fcol = BTN_SELECTED, FONT_SELECTED
                else col, fcol = BTN_NORMAL, FONT_NORMAL end
                d.editButton({index = k + 1, color = col, font_color = fcol})
            end
        end
    end
end

-- ------------------------------------------------------------------ scoring --

function zoneCount(tag, colour)
    local z = one(tag .. colour)
    if z == nil then return 0 end
    local n = 0
    for _, o in ipairs(z.getObjects()) do
        if o.type == "Card" then
            n = n + 1
        elseif o.type == "Deck" then
            n = n + #o.getObjects()
        end
    end
    return n
end

function piliCount(colour)
    local z = one(TAG_PILIS .. colour)
    if z == nil then return 0 end
    local n = 0
    for _, o in ipairs(z.getObjects()) do
        if o.getGMNotes() == "PILI:TOKEN" then n = n + 1 end
    end
    return n
end

function scoreRound()
    local seated = getSeatedPlayers()
    if dealt <= 0 or #seated == 0 then return end

    local bag = one("PILI:BAG")
    local lines = {}
    for _, c in ipairs(seated) do
        local cards = zoneCount(TAG_TRICKS, c)
        local tricks = math.floor(cards / #seated + 0.5)
        local bet = bids[c]
        if bet == nil then
            table.insert(lines, c .. " never bet")
        else
            local owed = math.abs(bet - tricks)
            if owed == 0 then
                table.insert(lines, c .. " bet " .. bet .. ", took " .. tricks .. " - clean")
            else
                table.insert(lines, c .. " bet " .. bet .. ", took " .. tricks ..
                    " - " .. owed .. " Pili" .. (owed == 1 and "" or "s"))
                givePilis(c, owed, bag)
            end
        end
    end
    broadcastToAll(table.concat(lines, "\n"), GOLD)
end

function givePilis(colour, n, bag)
    local z = one(TAG_PILIS .. colour)
    if bag == nil or z == nil then return end
    local p = z.getPosition()
    for i = 1, n do
        Wait.time(function()
            bag.takeObject({
                position = {p.x + math.random() * 0.9 - 0.45, p.y + 1.5 + i * 0.3,
                            p.z + math.random() * 0.9 - 0.45},
                rotation = {0, math.random(0, 359), 0}, smooth = true,
            })
        end, 0.12 * i)
    end
end

function checkGameOver()
    local worst, hits = 0, {}
    for _, c in ipairs(getSeatedPlayers()) do
        local n = piliCount(c)
        if n > worst then worst = n end
        if n >= PILI_LIMIT then table.insert(hits, c) end
    end
    if #hits == 0 then return false end

    local best = 9999
    for _, c in ipairs(getSeatedPlayers()) do
        best = math.min(best, piliCount(c))
    end
    local winners = {}
    for _, c in ipairs(getSeatedPlayers()) do
        if piliCount(c) == best then table.insert(winners, c) end
    end
    broadcastToAll(table.concat(hits, " & ") .. " reached " .. PILI_LIMIT ..
        " Pilis - game over. Fewest Pilis: " .. table.concat(winners, " & ") ..
        " on " .. best .. ".", HOT)
    return true
end

-- ------------------------------------------------------------------ round --

-- Reported bug: the play deck kept sliding off the table. It was resting in
-- the dealer's open cut-out (see the POS_* comment in build_save.py) with no
-- anchor, so any nearby physics nudge could walk it toward the unrailed edge
-- and off. Locking it at rest stops that; anything that will shuffle/deal/
-- take from a locked object needs to unlock it first, since Locked blocks
-- player drag but scripted calls are unaffected either way - unlocking is
-- just defensive.
-- Objects merged via putObject()/takeObject() can leave you holding a stale
-- reference to something Unity has already destroyed. TTS's own error for
-- that ("cannot access field Locked of userdata<LuaObject>") crashed the
-- entire calling chain (gather -> sweepAndDeal -> the whole round-advance),
-- not just this one assignment. pcall contains it to exactly that object.
function lockAtRest(obj)
    if obj == nil then return end
    pcall(function() obj.Locked = true end)
end

function unlockForOps(obj)
    if obj == nil then return end
    pcall(function() obj.Locked = false end)
end

function gather(tag, pos, thenShuffle, callback)
    local objs = cardsTagged(tag)
    if #objs == 0 then
        if callback then callback() end
        return
    end
    local base = table.remove(objs, 1)
    unlockForOps(base)
    base.setPosition({pos[1], pos[2] + 3.0, pos[3]})
    base.setRotation({0, 180, 180})
    for _, o in ipairs(objs) do
        unlockForOps(o)
        local r = base.putObject(o)
        if r ~= nil then base = r end
    end
    Wait.time(function()
        if base ~= nil then
            base.setGMNotes(tag)
            if thenShuffle and base.type == "Deck" then base.shuffle() end
            base.setPositionSmooth(pos)
            base.setRotationSmooth({0, 180, 180})
            Wait.time(function() lockAtRest(base) end, 1.0)
        end
        if callback then callback() end
    end, 1.1)
end

function nextRound()
    if busy then return end
    local seated = getSeatedPlayers()
    if #seated == 0 then
        broadcastToAll("Nobody is seated in a player colour.", HOT)
        return
    end
    busy = true

    if dealt > 0 then
        scoreRound()
    end

    Wait.time(function()
        if dealt > 0 and checkGameOver() then
            busy = false
            dealt = 0
            bids = {}
            buildDibberButtons()
            return
        end
        sweepAndDeal(seated)
    end, dealt > 0 and 1.6 or 0.1)
end

function sweepAndDeal(seated)
    -- old mission out of the way, if one was in play
    local live = missionInPlay()
    if live ~= nil then
        live.setPositionSmooth(POS_DISCARD)
        live.setRotationSmooth({0, 180, 180})
    end

    if not missionsOn then
        -- rulebook's own suggested first game: skip missions, deal 5 each,
        -- straight to betting. The mission deck is left completely alone.
        gather(TAG_PLAY, POS_PLAY, true, function()
            dealCards(seated, nil, 5)
        end)
        return
    end

    gather(TAG_PLAY, POS_PLAY, true, function()
        local mdeck = biggest(TAG_MISSION)
        if mdeck == nil then
            broadcastToAll("No mission cards left.", HOT)
            busy = false
            return
        end
        unlockForOps(mdeck)
        if mdeck.type == "Deck" then
            mdeck.takeObject({position = POS_REVEAL, rotation = {0, 180, 0}, smooth = true})
        else
            mdeck.setPositionSmooth(POS_REVEAL)
            mdeck.setRotationSmooth({0, 180, 0})
        end
        Wait.time(function() lockAtRest(biggest(TAG_MISSION)) end, 1.0)

        Wait.time(function()
            local m = missionInPlay()
            local n = 5
            if m ~= nil then
                n = tonumber(string.match(m.getDescription(), "%[deal (%d+)%]")) or 5
            end
            local name = m and m.getName() or "no mission"
            dealCards(seated, name, n)
        end, 1.4)
    end)
end

function missionInPlay()
    local best, bestd = nil, 1e9
    for _, o in ipairs(cardsTagged(TAG_MISSION)) do
        if o.type == "Card" then
            local p = o.getPosition()
            local d = (p.x - POS_REVEAL[1]) ^ 2 + (p.z - POS_REVEAL[3]) ^ 2
            if d < bestd then best, bestd = o, d end
        end
    end
    if bestd > 30 then return nil end
    return best
end

function dealCards(seated, missionName, n)
    local deck = biggest(TAG_PLAY)
    if deck == nil or deck.type ~= "Deck" then
        broadcastToAll("The play deck did not come back together.", HOT)
        busy = false
        return
    end
    unlockForOps(deck)

    local avail = countIn(deck)
    local maxn = math.floor(avail / #seated)
    if n > maxn then
        broadcastToAll("Only " .. avail .. " cards for " .. #seated ..
            " players - dealing " .. maxn .. " each instead of " .. n .. ".", HOT)
        n = maxn
    end
    if n < 1 then
        broadcastToAll("Too many players for the cards available.", HOT)
        busy = false
        return
    end

    dealt = n
    bids = {}
    buildDibberButtons()
    deck.shuffle()

    Wait.time(function()
        deck.deal(n)
        Wait.time(function()
            -- leftovers are set aside face down, still reachable for the
            -- missions that draw an extra card
            local rest = biggest(TAG_PLAY)
            if rest ~= nil then
                rest.setPositionSmooth(POS_ASIDE)
                rest.setRotationSmooth({0, 180, 180})
                Wait.time(function() lockAtRest(biggest(TAG_PLAY)) end, 1.0)
            end
            passDealer()

            -- Staggered on purpose: passDealer() just broadcast its own
            -- "X deals." message, and TTS's on-screen notification shows one
            -- message at a time - firing this one immediately would replace
            -- that one before anyone could read either. Terse status only;
            -- full instructions live in the rulebook on the table, not in
            -- something that flashes and fades in a few seconds.
            Wait.time(function()
                local label = missionName and ("Mission: " .. missionName .. ". ") or ""
                broadcastToAll(label .. n .. " cards each.", GOLD)
            end, 2.2)
            busy = false
        end, 1.0)
    end, 0.6)
end

-- ------------------------------------------------------------------ dealer --

function passDealer()
    local marker = one(TAG_DEALER)
    if marker == nil then return end
    local seated = getSeatedPlayers()
    if #seated == 0 then return end

    -- SEAT_ORDER is injected at build time from the SEATS table, so it is the
    -- real seating order round the table rather than whatever order TTS
    -- happens to hand back from getSeatedPlayers().
    local order = SEAT_ORDER
    if order == nil or #order == 0 then order = seated end

    -- nearest seat to the marker now, then step to the next seated colour
    local here, bestd = nil, 1e9
    local p = marker.getPosition()
    for _, c in ipairs(order) do
        local z = one(TAG_DIBBER .. c)
        if z ~= nil then
            local q = z.getPosition()
            local d = (p.x - q.x) ^ 2 + (p.z - q.z) ^ 2
            if d < bestd then here, bestd = c, d end
        end
    end

    local idx = 1
    for i, c in ipairs(order) do
        if c == here then idx = i end
    end
    local seatedNow = seatedSet()
    local nxt = nil
    for step = 1, #order do
        local c = order[((idx - 1 + step) % #order) + 1]
        if seatedNow[c] then nxt = c; break end
    end
    if nxt == nil then return end

    -- Placing the marker directly on the dibber's own coordinates (the old
    -- code here) put it on top of the dibber every single round after the
    -- first - the build-time placement was fixed once, but this runtime path
    -- runs every round and was never touched, so the bug never actually went
    -- away. Extrapolate past the dibber, away from the tray, using the two
    -- tiles' real positions - works for every seat, not just the one seat a
    -- build-time constant could describe.
    local dibber = one(TAG_DIBBER .. nxt)
    local tray = one(TAG_TRAY .. nxt)
    if dibber ~= nil and tray ~= nil then
        local dp, tp = dibber.getPosition(), tray.getPosition()
        marker.setPositionSmooth({
            dp.x + (dp.x - tp.x) * 0.6, dp.y + 1.0, dp.z + (dp.z - tp.z) * 0.6,
        })
    elseif dibber ~= nil then
        local dp = dibber.getPosition()
        marker.setPositionSmooth({dp.x, dp.y + 1.2, dp.z})
    end
    Turns.turn_color = nxt
    broadcastToAll(nxt .. " deals.", COOL)
end
