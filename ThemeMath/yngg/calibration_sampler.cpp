// Fast exploratory sampler for the current local yngg Python rules.
// This is not the supplied Linux server binary. Final configurations require
// canonical ThemeMath verification. BaseBet is fixed at 100000; disabled cells
// and DISORDER=1 are rejected because they are outside the verified replay scope.
// Usage: calibration_sampler ProjectDir PaidSpinCount Seed [TypeIndex=0] [Mode=0]
//                            [ExpectedRewards=0]
// Mode 0: paid base spins plus triggered sessions; 1/2: forced Free/Super sessions;
// Mode 3: paid base spins only (still counts free triggers).
// ExpectedRewards=1 integrates independent coin values, JP values, and clover
// multipliers conditionally on the sampled symbol types and geometry. It still
// consumes every original random tier draw. This estimates reward expectation,
// not the actual payout distribution, so payout volatility fields are omitted.
// Pot/Clover limits count all reveals across the feature. Coin minimums apply
// separately to each newly revealed batch, excluding persistent Pots.
// YNGG_RANDOM_LOG and YNGG_OUTCOME_LOG enable deterministic Python replay logs.
// TYPE 0 [Type0] PascalCase weight overrides match the authorized local extension.

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Mask = uint32_t;
ofstream RandomLog, OutcomeLog;
const Mask Full = (1u << 30) - 1;
constexpr long long BaseBet = 100000;
Mask Row0 = 0, Row4 = 0;
string Trim(string S) {
    auto A = S.find_first_not_of(" \t\r\n");
    if (A == string::npos)
        return "";
    return S.substr(A, S.find_last_not_of(" \t\r\n") - A + 1);
}
using Ini = map<string, map<string, string>>;
Ini ReadIni(string Path) {
    ifstream F(Path);
    if (!F)
        throw runtime_error("Cannot open " + Path);
    Ini Out;
    string L, Sec;
    while (getline(F, L)) {
        L = Trim(L);
        if (L.empty() || L[0] == '#' || L[0] == ';')
            continue;
        if (L[0] == '[') {
            Sec = L.substr(1, L.find(']') - 1);
            continue;
        }
        auto Eq = L.find('=');
        if (Eq != string::npos)
            Out[Sec][Trim(L.substr(0, Eq))] = Trim(L.substr(Eq + 1));
    }
    return Out;
}
vector<double> Parse(string S) {
    vector<double> V;
    stringstream SS(S);
    string X;
    while (getline(SS, X, ',')) {
        X = Trim(X);
        if (!X.empty())
            V.push_back(stod(X));
    }
    return V;
}
vector<int> ParseI(string S) {
    vector<int> V;
    for (double X : Parse(S))
        V.push_back((int)X);
    return V;
}
int ParseInteger(const string &Value, const string &Name) {
    size_t End = 0;
    int Parsed;
    try {
        Parsed = stoi(Value, &End);
    } catch (const exception &) {
        throw runtime_error(Name + " must be an integer");
    }
    if (End != Value.size())
        throw runtime_error(Name + " must be an integer");
    return Parsed;
}
template <typename Value>
double WeightedMean(const vector<Value> &Values, const vector<int> &Weights) {
    if (Values.empty() || Values.size() != Weights.size())
        throw runtime_error("Bonus values and weights must have equal nonzero lengths");
    long double Total = 0, WeightedTotal = 0;
    for (size_t Index = 0; Index < Values.size(); Index++) {
        if (Weights[Index] < 0 || Values[Index] <= 0)
            throw runtime_error("Bonus values must be positive and weights nonnegative");
        Total += Weights[Index];
        WeightedTotal += static_cast<long double>(Values[Index]) * Weights[Index];
    }
    if (Total <= 0)
        throw runtime_error("Bonus weights must have a positive total");
    return static_cast<double>(WeightedTotal / Total);
}
struct Rng {
    mt19937_64 State;
    Rng(uint64_t Seed) : State(Seed) {}
    uint64_t N(uint64_t Max) {
        auto Value = uniform_int_distribution<uint64_t>(0, Max - 1)(State);
        if (RandomLog.is_open())
            RandomLog << Max << " " << Value << "\n";
        return Value;
    }
    int Pick(const vector<int> &W) {
        int Total = 0;
        for (auto V : W)
            Total += V;
        if (Total <= 0)
            throw runtime_error("Bad weights");
        int Hit = N(Total);
        for (int I = 0; I < (int)W.size(); I++) {
            if (Hit < W[I])
                return I;
            Hit -= W[I];
        }
        throw runtime_error("Bad Pick");
    }
};
struct Reels {
    vector<int> Rate;
    array<vector<int>, 6> Normal, Special;
    vector<array<int, 30>> Fix, Zero;
    bool FixShuffle = false, ZeroShuffle = false;
};
Reels LoadReels(string Path) {
    auto Values = ReadIni(Path)["GENERAL_1"];
    Reels R;
    R.Rate = ParseI(Values["BASE_RATE"]);
    for (int C = 0; C < 6; C++) {
        R.Normal[C] = ParseI(Values["NORMAL_ROLL_" + to_string(C + 1)]);
        R.Special[C] = ParseI(Values["SP_ROLL_" + to_string(C + 1)]);
    }
    for (auto Pair : {make_pair("FIX", &R.Fix), make_pair("ZERO", &R.Zero)}) {
        int Count = stoi(Values[string(Pair.first) + "_NUM"]);
        for (int I = 1; I <= Count; I++) {
            auto A = ParseI(Values[string(Pair.first) + "_RESULT_" + to_string(I)]);
            array<int, 30> B;
            copy(A.begin(), A.end(), B.begin());
            Pair.second->push_back(B);
        }
    }
    R.FixShuffle = stoi(Values["FIX_DISORDER"]);
    R.ZeroShuffle = stoi(Values["ZERO_DISORDER"]);
    if (R.FixShuffle || R.ZeroShuffle)
        throw runtime_error("Calibration replay does not support DISORDER=1");
    return R;
}
struct Config {
    Reels Base, Free;
    array<vector<int>, 13> Pay;
    int PrizeRate = 1, Super = 200;
    int BonusMaxPotCount = 5, BonusMaxCloverCount = 3, BonusRevealMinCoinCount = 1;
    vector<int> Scatter, FreeScatter, BaseNoWin, BaseWin, FreeGold, FreeNoGold, Drop, FreeDrop,
        TypeWeights, CoinWeights, CloverWeights, JpWeights, FreeCounts, Retrigger;
    vector<double> CoinValues;
    vector<int> CloverValues, JpValues;
    bool ExpectedRewardsIntegrated = false;
    double CoinMean = 0, CloverMean = 0, JackpotMean = 0;
};
Config Load(string Root, int Index) {
    Config C;
    C.Base = LoadReels(Root + "/reel_config/yngg_rand_ex_" + to_string(Index) + ".conf");
    C.Free = LoadReels(Root + "/free_reel_config/yngg_free_rand_ex_" + to_string(Index) + ".conf");
    auto Main = ReadIni(Root + "/special/yngg_game_config.conf")["MAIN"];
    if (stoi(Main["COL_COUNT"]) != 6 || stoi(Main["ROW_COUNT"]) != 5 ||
        stoi(Main["ITEM_COUNT"]) != 13)
        throw runtime_error("Calibration sampler requires the current 6x5, 13-symbol layout");
    for (int I = 0; I < 13; I++)
        C.Pay[I] = ParseI(Main["ITEM_PRIZES_" + to_string(I)]);
    C.PrizeRate = stoi(Main["PRIZE_RATE"]);
    for (auto GridKey : {"GRID_DISABLES", "GRID_DISABLES_FREE"})
        for (auto Value : ParseI(Main[GridKey]))
            if (Value)
                throw runtime_error("Native sampler requires all GRID_DISABLES=0");
    auto Server = ReadIni(Root + "/special/yngg_game_server.conf");
    auto G = Server["Game Info"], T = Server[Index == 0 ? "Game Info" : to_string(Index)];
    C.Super = stoi(T["SuperScatterProbability"]);
    C.BonusMaxPotCount = ParseInteger(
        G.count("BonusMaxPotCount") ? G["BonusMaxPotCount"]
        : G.count("bonus_max_round") ? G["bonus_max_round"] : "5", "BonusMaxPotCount");
    C.BonusMaxCloverCount = ParseInteger(
        G.count("BonusMaxCloverCount") ? G["BonusMaxCloverCount"] : "3", "BonusMaxCloverCount");
    C.BonusRevealMinCoinCount = ParseInteger(
        G.count("BonusRevealMinCoinCount") ? G["BonusRevealMinCoinCount"] : "1", "BonusRevealMinCoinCount");
    if (C.BonusMaxPotCount < 0 || C.BonusMaxCloverCount < 0 || C.BonusRevealMinCoinCount < 0 ||
        C.BonusRevealMinCoinCount > 30)
        throw runtime_error("Invalid Bonus Pot/Clover caps or minimum coin count");
    C.FreeCounts = ParseI(G["FreeSpinCounts"]);
    C.Retrigger = ParseI(G["FreeSpinRetrigger"]);
    C.Scatter = ParseI(T["ScatterCountProbability"]);
    C.FreeScatter = ParseI(T["FreeScatterCountProbability"]);
    C.BaseNoWin = ParseI(T["BaseNoWinBonusCountProbability"]);
    C.BaseWin = ParseI(T["BaseWinBonusCountProbability"]);
    C.FreeGold = ParseI(T["FreeGoldenBonusCountProbability"]);
    C.FreeNoGold = ParseI(T["FreeNoGoldenBonusCountProbability"]);
    C.Drop = ParseI(T["DropSpecialSymbolProbability"]);
    C.FreeDrop = ParseI(T["FreeDropSpecialSymbolProbability"]);
    auto BonusIni = ReadIni(Root + "/special/yngg_bonus.conf");
    auto B = BonusIni["GENERAL"];
    if (Index == 0 && BonusIni.count("Type0")) {
        for (auto Names :
             {make_pair("BonusSymbolTypeProbability", "BONUS_SYMBOL_TYPE_PROBABILITY"),
              make_pair("BonusCoinMultipleProbability", "BONUS_COIN_MULTIPLE_PROBABILITY"),
              make_pair("BonusCloverMultipleProbability", "BONUS_CLOVER_MULTIPLE_PROBABILITY"),
              make_pair("BonusJpTypeProbability", "BONUS_JP_TYPE_PROBABILITY")})
            if (BonusIni["Type0"].count(Names.first))
                B[Names.second] = BonusIni["Type0"][Names.first];
    }
    C.TypeWeights = ParseI(B["BONUS_SYMBOL_TYPE_PROBABILITY"]);
    if (C.TypeWeights.size() != 4 ||
        any_of(C.TypeWeights.begin(), C.TypeWeights.end(), [](int Value) { return Value < 0; }) ||
        all_of(C.TypeWeights.begin(), C.TypeWeights.end(), [](int Value) { return Value == 0; }))
        throw runtime_error("Bonus symbol type weights require four nonnegative integers and a positive total");
    C.CoinValues = Parse(B["BONUS_COIN_MULTIPLE"]);
    C.CoinWeights = ParseI(B["BONUS_COIN_MULTIPLE_PROBABILITY"]);
    C.CloverValues = ParseI(B["BONUS_CLOVER_MULTIPLE"]);
    C.CloverWeights = ParseI(B["BONUS_CLOVER_MULTIPLE_PROBABILITY"]);
    C.JpValues = ParseI(B["BONUS_JP_MULTIPLE"]);
    C.JpWeights = ParseI(B["BONUS_JP_TYPE_PROBABILITY"]);
    C.CoinMean = WeightedMean(C.CoinValues, C.CoinWeights);
    C.CloverMean = WeightedMean(C.CloverValues, C.CloverWeights);
    C.JackpotMean = WeightedMean(C.JpValues, C.JpWeights);
    return C;
}
Mask Neighbor(Mask M) {
    return (((M & ~Row4) << 1) | ((M & ~Row0) >> 1) | (M << 5) | (M >> 5)) & Full;
}
struct Calc {
    double Win = 0;
    Mask Winning = 0, Remove = 0;
};
Calc Evaluate(const array<int, 30> &B, const Config &C) {
    Calc Out;
    array<Mask, 13> Masks{};
    for (int P = 0; P < 30; P++)
        Masks[B[P]] |= 1u << P;
    for (int Symbol = 3; Symbol <= 12; Symbol++) {
        Mask Left = Masks[Symbol] | Masks[1];
        while (Left) {
            Mask Region = Left & -Left, Last = 0;
            while (Last != Region) {
                Last = Region;
                Region |= Neighbor(Region) & Left;
            }
            Left &= ~Region;
            int Count = __builtin_popcount(Region);
            if (Count >= 5 && (Region & Masks[Symbol])) {
                int PayIndex = min(Count, 30) - 1;
                int Prize =
                    PayIndex < static_cast<int>(C.Pay[Symbol].size()) ? C.Pay[Symbol][PayIndex] : 0;
                if (Prize > 0) {
                    Out.Win +=
                        floor(static_cast<double>(BaseBet) * Prize / 10000 / max(C.PrizeRate, 1)) /
                        BaseBet;
                    Out.Winning |= Region;
                    Out.Remove |= Region | Masks[Symbol];
                }
            }
        }
    }
    return Out;
}
vector<int> Candidates(const array<int, 30> &B, Mask Removed, Mask Allowed = Full) {
    vector<int> V;
    for (int P = 0; P < 30; P++)
        if ((Allowed & (1u << P)) && !(Removed & (1u << P)) && B[P] >= 3 && B[P] <= 12)
            V.push_back(P);
    return V;
}
int Count(const array<int, 30> &B, int S) { return count(B.begin(), B.end(), S); }
void Convert(const array<int, 30> &B, int &Super, const Config &C, Rng &R) {
    if (Super >= 0)
        return;
    vector<int> Positions;
    for (int P = 0; P < 30; P++)
        if (B[P] == 0)
            Positions.push_back(P);
    if (Positions.size() && R.N(10000) < (unsigned)C.Super)
        Super = Positions[R.N(Positions.size())];
}
struct Outcome {
    double Cluster = 0, Bonus = 0;
    bool TriggerBonus = false, Seen = false;
    int Mode = 0, Spins = 0, Cascades = 0;
    Mask Golden = 0;
};
double Feature(Mask Golden, const Config &C, Rng &R) {
    array<int, 30> Types;
    array<double, 30> Mult{};
    Types.fill(-1);
    array<double, 30> Values{};
    Mask Persistent = 0;
    int PotCount = 0, CloverCount = 0;
    double Jp = 0;
    for (int Round = 0; Round < 100; Round++) {
        Mask New = Golden & ~Persistent, NewPots = 0;
        int RemainingRevealCount = __builtin_popcount(New), CoinCount = 0;
        if (RemainingRevealCount && RemainingRevealCount < C.BonusRevealMinCoinCount)
            throw runtime_error("Golden reveal batch cannot satisfy BonusRevealMinCoinCount");
        for (int Row = 0; Row < 5; Row++)
            for (int Col = 0; Col < 6; Col++) {
                int P = Col * 5 + Row;
                if (!(New & (1u << P)))
                    continue;
                auto W = C.TypeWeights;
                if (PotCount >= C.BonusMaxPotCount)
                    W[2] = 0;
                if (CloverCount >= C.BonusMaxCloverCount)
                    W[1] = 0;
                bool ForceCoin = C.BonusRevealMinCoinCount > 0 &&
                    (RemainingRevealCount <= max(C.BonusRevealMinCoinCount - CoinCount, 0) ||
                     all_of(W.begin(), W.end(), [](int Weight) { return Weight == 0; }));
                int Kind = ForceCoin ? 0 : R.Pick(W);
                RemainingRevealCount--;
                Types[P] = Kind;
                Values[P] = 0;
                Mult[P] = 0;
                if (Kind == 0) {
                    CoinCount++;
                    int Tier = R.Pick(C.CoinWeights);
                    Values[P] = C.ExpectedRewardsIntegrated ? C.CoinMean : C.CoinValues[Tier];
                } else if (Kind == 1) {
                    CloverCount++;
                    int Tier = R.Pick(C.CloverWeights);
                    Mult[P] = C.ExpectedRewardsIntegrated ? C.CloverMean : C.CloverValues[Tier];
                } else if (Kind == 2) {
                    PotCount++;
                    NewPots |= 1u << P;
                } else {
                    int Tier = R.Pick(C.JpWeights);
                    Jp += C.ExpectedRewardsIntegrated ? C.JackpotMean : C.JpValues[Tier];
                }
            }
        for (int Row = 0; Row < 5; Row++)
            for (int Col = 0; Col < 6; Col++) {
                int P = Col * 5 + Row;
                if ((New & (1u << P)) && Types[P] == 1)
                    for (int Q = 0; Q < 30; Q++)
                        if ((Types[Q] == 0 || Types[Q] == 2) && abs(Q / 5 - Col) <= 1 &&
                            abs(Q % 5 - Row) <= 1)
                            Values[Q] *= Mult[P];
            }
        for (int Col = 0; Col < 6; Col++)
            for (int Row = 4; Row >= 0; Row--) {
                int P = Col * 5 + Row;
                if ((NewPots & (1u << P))) {
                    double Sum = 0;
                    for (int Q = 0; Q < 30; Q++)
                        if (Q != P && (Types[Q] == 0 || Types[Q] == 2))
                            Sum += Values[Q];
                    Values[P] = Sum;
                }
            }
        Persistent |= NewPots;
        if (!NewPots || Persistent == Golden)
            break;
        if (Round == 99)
            throw runtime_error("Max feature rounds");
    }
    double Sum = Jp;
    for (int P = 0; P < 30; P++)
        if (Types[P] == 0 || Types[P] == 2)
            Sum += Values[P];
    return nearbyint(Sum * BaseBet) / BaseBet;
}
Outcome Spin(const Config &C, Rng &R, int Mode, Mask Golden = 0, int Remaining = 0,
             bool Seen = false) {
    bool Free = Mode > 0;
    const Reels &Re = Free ? C.Free : C.Base;
    int Source = R.Pick(Re.Rate);
    auto *Rolls = &Re.Normal;
    array<int, 30> B;
    array<int, 6> Next;
    int Super = -1;
    if (Source < 2) {
        if (Source == 1)
            Rolls = &Re.Special;
        for (int Col = 0; Col < 6; Col++) {
            int Start = R.N((*Rolls)[Col].size());
            for (int Row = 0; Row < 5; Row++)
                B[Col * 5 + Row] = (*Rolls)[Col][(Start + Row) % (*Rolls)[Col].size()];
            Next[Col] = (Start + 5) % (*Rolls)[Col].size();
        }
    } else {
        auto &Results = Source == 2 ? Re.Fix : Re.Zero;
        B = Results[R.N(Results.size())];
        bool Shuffle = Source == 2 ? Re.FixShuffle : Re.ZeroShuffle;
        if (Shuffle)
            for (int Col = 0; Col < 6; Col++)
                shuffle(B.begin() + Col * 5, B.begin() + (Col + 1) * 5, R.State);
        for (int Col = 0; Col < 6; Col++)
            Next[Col] = R.N((*Rolls)[Col].size());
    }
    if (Source < 2) {
        Calc Initial = Evaluate(B, C);
        auto Can = Candidates(B, Initial.Remove);
        int Sc = min(R.Pick(Free ? C.FreeScatter : C.Scatter), (int)Can.size());
        vector<int> Symbols(Sc, 0);
        if (Sc <= 2 && Sc < (int)Can.size()) {
            auto W = Free ? (Golden ? C.FreeGold : C.FreeNoGold)
                          : (Initial.Win > 0 ? C.BaseWin : C.BaseNoWin);
            if (R.Pick(W))
                Symbols.push_back(2);
        }
        for (int Symbol : Symbols) {
            int K = R.N(Can.size()), P = Can[K];
            B[P] = Symbol;
            Can.erase(Can.begin() + K);
        }
    }
    if (!Free)
        Convert(B, Super, C, R);
    Outcome O;
    O.Seen = Seen;
    for (int Iter = 0; Iter < 100; Iter++) {
        Calc E = Evaluate(B, C);
        if (E.Win <= 0 || E.Winning == 0)
            break;
        O.Cluster += E.Win;
        O.Cascades++;
        Golden |= E.Winning;
        Mask Dropped = 0;
        int NewSuper = -1;
        for (int Col = 0; Col < 6; Col++) {
            int Write = 0;
            for (int Row = 0; Row < 5; Row++) {
                int Old = Col * 5 + Row;
                if (!(E.Remove & (1u << Old))) {
                    B[Col * 5 + Write] = B[Old];
                    if (Super == Old)
                        NewSuper = Col * 5 + Write;
                    Write++;
                }
            }
            for (int Row = Write; Row < 5; Row++) {
                int P = Col * 5 + Row;
                B[P] = (*Rolls)[Col][Next[Col]];
                Next[Col] = (Next[Col] + 1) % (*Rolls)[Col].size();
                Dropped |= 1u << P;
            }
        }
        Super = NewSuper;
        if (!Count(B, 2) && Count(B, 0) < 3) {
            Calc New = Evaluate(B, C);
            auto Can = Candidates(B, New.Remove, Dropped);
            for (int P : Can) {
                int Type = R.Pick(Free ? C.FreeDrop : C.Drop);
                if (!Type)
                    continue;
                B[P] = Type == 1 ? 0 : 2;
                if (!Free && Type == 1)
                    Convert(B, Super, C, R);
                break;
            }
        }
        if (Iter == 99)
            throw runtime_error("Max cascade");
    }
    if (Free && Remaining == 1 && !Seen && !Count(B, 2)) {
        auto Can = Candidates(B, 0);
        if (Can.size())
            B[Can[R.N(Can.size())]] = 2;
    }
    O.TriggerBonus = Golden && Count(B, 2);
    if (O.TriggerBonus) {
        O.Bonus = Feature(Golden, C, R);
        if (Mode < 2)
            Golden = 0;
    }
    O.Seen = Seen || Count(B, 2);
    O.Golden = Golden;
    int Sc = Count(B, 0);
    if (Free)
        O.Spins = C.Retrigger[min(Sc, 3)];
    else if (Sc >= 3) {
        O.Mode = Super >= 0 ? 2 : 1;
        O.Spins = C.FreeCounts[O.Mode - 1];
    }
    return O;
}
struct Metric {
    long double Sum = 0, Square = 0;
    void Add(double V) {
        Sum += V;
        Square += (long double)V * V;
    }
    double Mean(long long N) { return (double)(Sum / N); }
    double Se(long long N) {
        if (N < 2)
            return 0;
        return sqrt(max((long double)0, (Square - Sum * Sum / N) / (N - 1) / N));
    }
};
struct Metrics {
    array<Metric, 7> Values;
    long long BaseBonusTriggers = 0, FreeTriggers = 0, SuperTriggers = 0, FreeSpins = 0,
              SuperSpins = 0;
    vector<double> Bonus;
};
void Run(const Config &C, Rng &R, long long N, Metrics &M, int ForcedMode = 0) {
    for (long long I = 0; I < N; I++) {
        array<double, 7> V{};
        Outcome Base;
        if (!ForcedMode || ForcedMode == 3) {
            Base = Spin(C, R, 0);
            V[0] = Base.Cluster;
            V[1] = Base.Bonus;
            if (Base.TriggerBonus) {
                M.BaseBonusTriggers++;
                M.Bonus.push_back(Base.Bonus);
            }
        } else {
            Base.Mode = ForcedMode;
            Base.Spins = C.FreeCounts[ForcedMode - 1];
        }
        if (ForcedMode == 3 && Base.Spins) {
            if (Base.Mode == 1)
                M.FreeTriggers++;
            else
                M.SuperTriggers++;
            Base.Spins = 0;
        }
        if (Base.Spins) {
            int Mode = Base.Mode;
            if (Mode == 1)
                M.FreeTriggers++;
            else
                M.SuperTriggers++;
            int Remaining = Base.Spins;
            Mask Golden = 0;
            bool Seen = false;
            while (Remaining > 0) {
                Outcome Free = Spin(C, R, Mode, Golden, Remaining, Seen);
                Remaining--;
                Remaining += Free.Spins;
                Golden = Free.Golden;
                Seen = Free.Seen;
                int Offset = Mode == 1 ? 2 : 4;
                V[Offset] += Free.Cluster;
                V[Offset + 1] += Free.Bonus;
                if (Mode == 1)
                    M.FreeSpins++;
                else
                    M.SuperSpins++;
                if (Remaining > 10000)
                    throw runtime_error("Runaway free");
            }
        }
        for (int K = 0; K < 6; K++)
            V[6] += V[K];
        if (OutcomeLog.is_open()) {
            // Integer monetary units make the Python replay comparison exact.
            for (double Value : V) {
                double Money = Value * BaseBet;
                if (!isfinite(Money) || abs(Money) > 9007199254740991.0)
                    throw runtime_error("Monetary result exceeds the exact replay integer range");
                OutcomeLog << llround(Money) << " ";
            }
            OutcomeLog << Base.Mode << " " << Base.TriggerBonus << "\n";
        }
        for (int K = 0; K < 7; K++)
            M.Values[K].Add(V[K]);
    }
}
int main(int Argc, char **Argv) {
    try {
        if (Argc < 4 || Argc > 7) {
            cerr << "usage: calibration_sampler ProjectDir PaidSpins Seed [TypeIndex=0] "
                    "[ForcedMode=0] [ExpectedRewards=0]\n";
            return 2;
        }
        if (getenv("YNGG_RANDOM_LOG"))
            RandomLog.open(getenv("YNGG_RANDOM_LOG"));
        if (getenv("YNGG_OUTCOME_LOG"))
            OutcomeLog.open(getenv("YNGG_OUTCOME_LOG"));
        for (int C = 0; C < 6; C++) {
            Row0 |= 1u << (C * 5);
            Row4 |= 1u << (C * 5 + 4);
        }
        auto Start = chrono::steady_clock::now();
        Config C = Load(Argv[1], Argc > 4 ? stoi(Argv[4]) : 0);
        long long N = stoll(Argv[2]);
        if (N <= 0)
            throw runtime_error("Sample count must be positive");
        int Mode = Argc > 5 ? stoi(Argv[5]) : 0;
        if (Mode < 0 || Mode > 3)
            throw runtime_error("Mode must be 0, 1, 2, or 3");
        int ExpectedRewards = Argc > 6 ? stoi(Argv[6]) : 0;
        if (ExpectedRewards != 0 && ExpectedRewards != 1)
            throw runtime_error("ExpectedRewards must be 0 or 1");
        C.ExpectedRewardsIntegrated = ExpectedRewards == 1;
        Rng R(stoull(Argv[3]));
        Metrics M;
        Run(C, R, N, M, Mode);
        const char *Names[] = {"BaseClusterRtp",
                               "BaseBonusRtp",
                               "FreeClusterRtp",
                               "FreeBonusRtp",
                               "SuperFreeClusterRtp",
                               "SuperFreeBonusRtp",
                               "Rtp"};
        cout << setprecision(12) << "{\"BaseBet\":" << BaseBet << ",\"BaseSpinCount\":" << N
             << ",\"RewardSampling\":\""
             << (C.ExpectedRewardsIntegrated ? "ConditionalExpectation" : "FullRandom")
             << "\",\"ExpectedRewardsIntegrated\":"
             << (C.ExpectedRewardsIntegrated ? "true" : "false");
        for (int K = 0; K < 7; K++)
            cout << ",\"" << Names[K] << "\":" << M.Values[K].Mean(N) << ",\"" << Names[K]
                 << "StandardError\":" << M.Values[K].Se(N);
        cout << ",\"BaseBonusFrequency\":" << (double)M.BaseBonusTriggers / N
             << ",\"FreeFrequency\":" << (double)M.FreeTriggers / N
             << ",\"SuperFreeFrequency\":" << (double)M.SuperTriggers / N
             << ",\"FreeSpinCount\":" << M.FreeSpins << ",\"SuperFreeSpinCount\":" << M.SuperSpins;
        if (M.Bonus.size()) {
            if (!C.ExpectedRewardsIntegrated)
                sort(M.Bonus.begin(), M.Bonus.end());
            double Sum = 0, Square = 0;
            for (double V : M.Bonus) {
                Sum += V;
                Square += V * V;
            }
            cout << ",\"BaseBonusConditionalMean\":" << Sum / M.Bonus.size();
            if (!C.ExpectedRewardsIntegrated) {
                cout << ",\"BaseBonusConditionalStdDev\":"
                     << sqrt(max(0.0, Square / M.Bonus.size() - pow(Sum / M.Bonus.size(), 2)));
                for (auto P : {50, 90, 95, 99})
                    cout << ",\"BaseBonusP" << P
                         << "\":" << M.Bonus[min(M.Bonus.size() - 1, M.Bonus.size() * P / 100)];
                cout << ",\"BaseBonusMax\":" << M.Bonus.back();
            }
        }
        cout << ",\"Seconds\":"
             << chrono::duration<double>(chrono::steady_clock::now() - Start).count() << "}\n";
    } catch (exception &E) {
        cerr << E.what() << "\n";
        return 1;
    }
}
