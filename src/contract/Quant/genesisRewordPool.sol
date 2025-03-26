// SPDX-License-Identifier: BUSL-1.1

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "../lib/SafeMath.sol";
import "../interfaces/IBasisAsset.sol";

contract GenesisRewardPool is ReentrancyGuard {
    using SafeMath for uint256;
    using SafeERC20 for IERC20;

    // governance
    address public operator;

    // Info of each user.
    struct UserInfo {
        uint256 amount; // How many LP tokens the user has provided.
        uint256 rewardDebt; // Reward debt. See explanation below.
    }

    // Info of each pool.
    struct PoolInfo {
        IERC20 token; // Address of LP token contract.
        uint256 depFee; // deposit fee that is applied to created pool.
        uint256 allocPoint; // How many allocation points assigned to this pool. QUANTs to distribute per block.
        uint256 lastRewardTime; // Last time that QUANTs distribution occurs.
        uint256 accQuantPerShare; // Accumulated QUANTs per share, times 1e18. See below.
        bool isStarted; // if lastRewardTime has passed
        uint256 poolQuantPerSec; // rewards per second for pool (acts as allocPoint)
        uint256 currentDeposit; // Current net deposit (TVL) in this pool.
        uint256 maxDeposit; // Highest deposit value ever recorded for this pool.
    }

    IERC20 public quant;
    address public devFund;

    // Info of each pool.
    PoolInfo[] public poolInfo;

    // Info of each user that stakes LP tokens.
    mapping(uint256 => mapping(address => UserInfo)) public userInfo;

    // Total allocation points. Must be the sum of all allocation points in all pools.
    uint256 public totalAllocPoint = 0;

    // The time when QUANT mining starts.
    uint256 public poolStartTime;

    // The time when QUANT mining ends.
    uint256 public poolEndTime;
    uint256 public quantPerSecond = 0 ether;
    uint256 public runningTime = 7 days;

    event Deposit(address indexed user, uint256 indexed pid, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed pid, uint256 amount);
    event EmergencyWithdraw(
        address indexed user,
        uint256 indexed pid,
        uint256 amount
    );
    event RewardPaid(address indexed user, uint256 amount);

    constructor(address _quant, address _devFund, uint256 _poolStartTime) {
        require(
            block.timestamp < _poolStartTime,
            "pool cant be started in the past"
        );
        if (_quant != address(0)) quant = IERC20(_quant);
        if (_devFund != address(0)) devFund = _devFund;

        poolStartTime = _poolStartTime;
        poolEndTime = _poolStartTime + runningTime;
        operator = msg.sender;
        devFund = _devFund;

        // create all the pools (daily rewards divided by 86400 seconds)
        add(0.248015873 ether, 0, IERC20(0xa774bf15419499d1e9B227188eCa366ff55Af4bE), false, 0);    // Quant-scUSD 30% 21,428.57 tokens/day

        add(0.082671958 ether, 200, IERC20(0x3333b97138D4b086720b5aE8A7844b1345a33333), false, 0);  // Shadow 10%  7,142.86 tokens/day

        add(0.066115702 ether, 200, IERC20(0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38), false, 0);  // wS 8%       5,714.29 tokens/day

        add(0.132231404 ether, 200, IERC20(0xd3DCe716f3eF535C5Ff8d041c1A41C3bd89b97aE), false, 0);  // scUSD 16%   11,428.57 tokens/day

        add(0.041322314 ether, 200, IERC20(0x9fDbC3f8Abc05Fa8f3Ad3C17D2F806c1230c4564), false, 0);  // GOGLZ 5%    3,571.43 tokens/day

        add(0.041322314 ether, 200, IERC20(0xf26Ff70573ddc8a90Bd7865AF8d7d70B8Ff019bC), false, 0);  // EGGS 5%     3,571.43 tokens/day

        add(0.132231404 ether, 200, IERC20(0xb1e25689D55734FD3ffFc939c4C3Eb52DFf8A794), false, 0);  // OS 16%      11,428.57 tokens/day

        add(0.016528926 ether, 200, IERC20(0xe920d1DA9A4D59126dC35996Ea242d60EFca1304), false, 0);  // DERP 2%     1,428.57 tokens/day

        add(0.066115702 ether, 200, IERC20(0x3333111A391cC08fa51353E9195526A70b333333), false, 0);  // x33 8%      5,714.29 tokens/day
    }

    modifier onlyOperator() {
        require(
            operator == msg.sender,
            "GenesisRewardPool: caller is not the operator"
        );
        _;
    }

    function poolLength() external view returns (uint256) {
        return poolInfo.length;
    }

    function checkPoolDuplicate(IERC20 _token) internal view {
        uint256 length = poolInfo.length;
        for (uint256 pid = 0; pid < length; ++pid) {
            require(
                poolInfo[pid].token != _token,
                "GenesisRewardPool: existing pool?"
            );
        }
    }

    // bulk add pools
    function addBulk(
        uint256[] calldata _allocPoints,
        uint256[] calldata _depFees,
        IERC20[] calldata _tokens,
        bool _withUpdate,
        uint256 _lastRewardTime
    ) external onlyOperator {
        require(
            _allocPoints.length == _depFees.length &&
                _allocPoints.length == _tokens.length,
            "GenesisRewardPool: invalid length"
        );
        for (uint256 i = 0; i < _allocPoints.length; i++) {
            add(
                _allocPoints[i],
                _depFees[i],
                _tokens[i],
                _withUpdate,
                _lastRewardTime
            );
        }
    }

    // Add new lp to the pool. Can only be called by operator.
    function add(
        uint256 _allocPoint,
        uint256 _depFee,
        IERC20 _token,
        bool _withUpdate,
        uint256 _lastRewardTime
    ) public onlyOperator {
        require(
            _depFee <= 200,
            "GenesisRewardPool: deposit fee cannot exceed 2%"
        );
        require(
            address(_token) != address(0) && address(_token).code.length > 0,
            "GenesisRewardPool: token must be a valid contract"
        );
        checkPoolDuplicate(_token);
        if (_withUpdate) {
            massUpdatePools();
        }
        if (block.timestamp < poolStartTime) {
            // chef is sleeping
            if (_lastRewardTime == 0) {
                _lastRewardTime = poolStartTime;
            } else {
                if (_lastRewardTime < poolStartTime) {
                    _lastRewardTime = poolStartTime;
                }
            }
        } else {
            // chef is cooking
            if (_lastRewardTime == 0 || _lastRewardTime < block.timestamp) {
                _lastRewardTime = block.timestamp;
            }
        }
        bool _isStarted = (_lastRewardTime <= poolStartTime) ||
            (_lastRewardTime <= block.timestamp);
        poolInfo.push(
            PoolInfo({
                token: _token,
                depFee: _depFee,
                allocPoint: _allocPoint,
                poolQuantPerSec: _allocPoint,
                lastRewardTime: _lastRewardTime,
                accQuantPerShare: 0,
                isStarted: _isStarted,
                currentDeposit: 0,
                maxDeposit: 0
            })
        );

        if (_isStarted) {
            totalAllocPoint = totalAllocPoint.add(_allocPoint);
            quantPerSecond = quantPerSecond.add(_allocPoint);
        }
    }

    // Update the given pool's QUANT allocation point. Can only be called by the operator.
    function set(
        uint256 _pid,
        uint256 _allocPoint,
        uint256 _depFee
    ) public onlyOperator {
        massUpdatePools();

        PoolInfo storage pool = poolInfo[_pid];
        require(_depFee <= 200); // deposit fee cant be more than 2%;
        pool.depFee = _depFee;

        if (pool.isStarted) {
            totalAllocPoint = totalAllocPoint.sub(pool.allocPoint).add(
                _allocPoint
            );
            quantPerSecond = quantPerSecond.sub(pool.poolQuantPerSec).add(
                _allocPoint
            );
        }
        pool.allocPoint = _allocPoint;
        pool.poolQuantPerSec = _allocPoint;
    }

    function bulkSet(
        uint256[] calldata _pids,
        uint256[] calldata _allocPoints,
        uint256[] calldata _depFees
    ) external onlyOperator {
        require(
            _pids.length == _allocPoints.length &&
                _pids.length == _depFees.length,
            "GenesisRewardPool: invalid length"
        );
        for (uint256 i = 0; i < _pids.length; i++) {
            set(_pids[i], _allocPoints[i], _depFees[i]);
        }
    }

    // Return accumulate rewards over the given _from to _to block.
    function getGeneratedReward(
        uint256 _fromTime,
        uint256 _toTime
    ) public view returns (uint256) {
        if (_fromTime >= _toTime) return 0;
        if (_toTime >= poolEndTime) {
            if (_fromTime >= poolEndTime) return 0;
            if (_fromTime <= poolStartTime)
                return poolEndTime.sub(poolStartTime).mul(quantPerSecond);
            return poolEndTime.sub(_fromTime).mul(quantPerSecond);
        } else {
            if (_toTime <= poolStartTime) return 0;
            if (_fromTime <= poolStartTime)
                return _toTime.sub(poolStartTime).mul(quantPerSecond);
            return _toTime.sub(_fromTime).mul(quantPerSecond);
        }
    }

    // View function to see pending QUANTs on frontend.
    function pendingQUANT(
        uint256 _pid,
        address _user
    ) external view returns (uint256) {
        PoolInfo storage pool = poolInfo[_pid];
        UserInfo storage user = userInfo[_pid][_user];
        uint256 accQuantPerShare = pool.accQuantPerShare;
        uint256 tokenSupply = pool.token.balanceOf(address(this));
        if (block.timestamp > pool.lastRewardTime && tokenSupply != 0) {
            uint256 _generatedReward = getGeneratedReward(
                pool.lastRewardTime,
                block.timestamp
            );
            uint256 _quantReward = _generatedReward.mul(pool.allocPoint).div(
                totalAllocPoint
            );
            accQuantPerShare = accQuantPerShare.add(
                _quantReward.mul(1e18).div(tokenSupply)
            );
        }
        return user.amount.mul(accQuantPerShare).div(1e18).sub(user.rewardDebt);
    }

    function massUpdatePools() public {
        uint256 length = poolInfo.length;
        for (uint256 pid = 0; pid < length; ++pid) {
            updatePool(pid);
        }
    }

    // massUpdatePoolsInRange
    function massUpdatePoolsInRange(uint256 _fromPid, uint256 _toPid) public {
        require(_fromPid <= _toPid, "GenesisRewardPool: invalid range");
        for (uint256 pid = _fromPid; pid <= _toPid; ++pid) {
            updatePool(pid);
        }
    }

    // Update reward variables of the given pool to be up-to-date.
    function updatePool(uint256 _pid) private {
        PoolInfo storage pool = poolInfo[_pid];
        if (block.timestamp <= pool.lastRewardTime) {
            return;
        }
        uint256 tokenSupply = pool.token.balanceOf(address(this));
        if (tokenSupply == 0) {
            pool.lastRewardTime = block.timestamp;
            return;
        }
        if (!pool.isStarted) {
            pool.isStarted = true;
            totalAllocPoint = totalAllocPoint.add(pool.allocPoint);
            quantPerSecond = quantPerSecond.add(pool.poolQuantPerSec);
        }
        if (totalAllocPoint > 0) {
            uint256 _generatedReward = getGeneratedReward(
                pool.lastRewardTime,
                block.timestamp
            );
            uint256 _quantReward = _generatedReward.mul(pool.allocPoint).div(
                totalAllocPoint
            );
            pool.accQuantPerShare = pool.accQuantPerShare.add(
                _quantReward.mul(1e18).div(tokenSupply)
            );
        }
        pool.lastRewardTime = block.timestamp;
    }

    function setDevFund(address _devFund) public onlyOperator {
        devFund = _devFund;
    }

    // Deposit LP tokens.
    function deposit(uint256 _pid, uint256 _amount) public nonReentrant {
        address _sender = msg.sender;
        PoolInfo storage pool = poolInfo[_pid];
        UserInfo storage user = userInfo[_pid][_sender];
        updatePool(_pid);
        if (user.amount > 0) {
            uint256 _pending = user
                .amount
                .mul(pool.accQuantPerShare)
                .div(1e18)
                .sub(user.rewardDebt);
            if (_pending > 0) {
                safeQuantTransfer(_sender, _pending);
                emit RewardPaid(_sender, _pending);
            }
        }
        if (_amount > 0) {
            // Transfer deposit tokens from user.
            pool.token.safeTransferFrom(_sender, address(this), _amount);
            // Calculate deposit fee.
            uint256 depositDebt = _amount.mul(pool.depFee).div(10000);
            // Net deposit after fee.
            uint256 netDeposit = _amount.sub(depositDebt);
            // Update user amount.
            user.amount = user.amount.add(netDeposit);
            // Transfer fee to devFund.
            pool.token.safeTransfer(devFund, depositDebt);
            // Update pool's current deposit tracking.
            pool.currentDeposit = pool.currentDeposit.add(netDeposit);
            // Update maxDeposit if currentDeposit is higher.
            if (pool.currentDeposit > pool.maxDeposit) {
                pool.maxDeposit = pool.currentDeposit;
            }
        }
        user.rewardDebt = user.amount.mul(pool.accQuantPerShare).div(1e18);
        emit Deposit(_sender, _pid, _amount);
    }

    // Withdraw LP tokens.
    function withdraw(uint256 _pid, uint256 _amount) public nonReentrant {
        address _sender = msg.sender;
        PoolInfo storage pool = poolInfo[_pid];
        UserInfo storage user = userInfo[_pid][_sender];
        require(user.amount >= _amount, "withdraw: not good");
        updatePool(_pid);
        uint256 _pending = user.amount.mul(pool.accQuantPerShare).div(1e18).sub(
            user.rewardDebt
        );
        if (_pending > 0) {
            safeQuantTransfer(_sender, _pending);
            emit RewardPaid(_sender, _pending);
        }
        if (_amount > 0) {
            user.amount = user.amount.sub(_amount);
            // Subtract the withdrawn amount from the pool's currentDeposit
            pool.currentDeposit = pool.currentDeposit.sub(_amount);
            pool.token.safeTransfer(_sender, _amount);
        }
        user.rewardDebt = user.amount.mul(pool.accQuantPerShare).div(1e18);
        emit Withdraw(_sender, _pid, _amount);
    }

    // Withdraw without caring about rewards. EMERGENCY ONLY.
    function emergencyWithdraw(uint256 _pid) public nonReentrant {
        PoolInfo storage pool = poolInfo[_pid];
        UserInfo storage user = userInfo[_pid][msg.sender];
        uint256 _amount = user.amount;
        user.amount = 0;
        user.rewardDebt = 0;
        pool.token.safeTransfer(msg.sender, _amount);
        emit EmergencyWithdraw(msg.sender, _pid, _amount);
    }

    // Safe quant transfer function, just in case if rounding error causes pool to not have enough QUANTs.
    function safeQuantTransfer(address _to, uint256 _amount) internal {
        uint256 _quantBal = quant.balanceOf(address(this));
        if (_quantBal > 0) {
            if (_amount > _quantBal) {
                quant.safeTransfer(_to, _quantBal);
            } else {
                quant.safeTransfer(_to, _amount);
            }
        }
    }

    function setOperator(address _operator) external onlyOperator {
        operator = _operator;
    }

    function governanceRecoverUnsupported(
        IERC20 _token,
        uint256 amount,
        address to
    ) external onlyOperator {
        if (block.timestamp < poolEndTime + 30 days) {
            // Before 30 days after pool end, ensure you can't recover any pool tokens.
            uint256 length = poolInfo.length;
            for (uint256 pid = 0; pid < length; ++pid) {
                PoolInfo storage pool = poolInfo[pid];
                require(
                    _token != pool.token,
                    "GenesisRewardPool: Token cannot be pool token"
                );
            }
            _token.safeTransfer(to, amount);
        } else {
            // After 30 days, check if token is a pool token and ensure pool is empty
            uint256 length = poolInfo.length;
            for (uint256 pid = 0; pid < length; ++pid) {
                PoolInfo storage pool = poolInfo[pid];
                if (_token == pool.token) {
                    require(
                        pool.currentDeposit == 0,
                        "GenesisRewardPool: Pool must be empty to recover token"
                    );
                    break;
                }
            }

            // If it's the reward token, burn it
            if (address(_token) == address(quant)) {
                // Burn the tokens instead of transferring.
                // Make sure the reward token (quant) implements the burn function.
                quant.safeTransfer(address(0), amount);
            } else {
                // For any other token, proceed with a safe transfer.
                _token.safeTransfer(to, amount);
            }
        }
    }
}