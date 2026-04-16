#ifndef FX_FXROBOT_H_
#define FX_FXROBOT_H_


#include "FXRobotDef.h"

#define  _USER_IF_TAG_

#ifdef _USER_IF_TAG_

FX_BOOL  LOADMvCfg(FX_CHAR* path, FX_INT32L TYPE[2], FX_DOUBLE GRV[2][3], FX_DOUBLE DH[2][8][4], FX_DOUBLE PNVA[2][7][4], FX_DOUBLE BD[2][4][3],
	FX_DOUBLE Mass[2][7], FX_DOUBLE MCP[2][7][3], FX_DOUBLE I[2][7][6]);

#endif // _USER_IF_TAG_
////////////////////////////////////////////////////////////////////////////////////////////////
FX_BOOL  FX_Robot_Init_Type(FX_INT32L RobotSerial, FX_INT32L RobotType);
FX_BOOL  FX_Robot_Init_Kine(FX_INT32L RobotSerial, FX_DOUBLE DH[8][4]);
FX_BOOL  FX_Robot_Init_Lmt(FX_INT32L RobotSerial, FX_DOUBLE PNVA[7][4], FX_DOUBLE J67[4][3]);
FX_BOOL  FX_Robot_Init_Dyna(FX_INT32L RobotSerial, Vect3 GRV, FX_DOUBLE Mass[7],Vect3 MCP[7], Vect6 I[7]);
FX_BOOL  FX_Robot_Init_Dyna_Set_VirTool(FX_INT32L RobotSerial, FX_DOUBLE Mass, Vect3 MCP, Vect6 I);
////////////////////////////////////////////////////////////////////////////////////////////////
FX_BOOL  FX_Robot_Tool_Set(FX_INT32L RobotSerial, Matrix4 tool);
FX_BOOL  FX_Robot_Tool_Rmv(FX_INT32L RobotSerial);
FX_BOOL  FX_Robot_Tool_SetDyn(FX_INT32L RobotSerial, FX_DOUBLE Mass,Vect3 MCP, Vect6 I);
FX_BOOL  FX_Robot_Tool_RmvDyn(FX_INT32L RobotSerial);
////////////////////////////////////////////////////////////////////////////////////////////////
FX_BOOL  FX_Robot_Kine_FK(FX_INT32L RobotSerial, FX_DOUBLE joints[7], Matrix4 pgos);
FX_BOOL  FX_Robot_Kine_Jacb(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_Jacobi* jcb);
FX_BOOL  FX_Robot_Kine_JacbJacbDot(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE joints_vel[7], FX_Jacobi* jcb, FX_Jacobi* jcb_dot);
FX_BOOL  FX_Robot_Kine_IK(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para);
FX_BOOL  FX_Robot_Kine_IK(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para, FX_DOUBLE ref_rpy[3]);
FX_BOOL  FX_Robot_Kine_IK_NSP(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para);
////////////////////////////////////////////////////////////////////////////////////////////////
FX_BOOL  FX_Robot_Dyna_CalBase(FX_INT32L RobotSerial, Vect7 angle);
FX_BOOL  FX_Robot_Dyna_ID_Fix(FX_INT32L RobotSerial,Vect7 qd, Vect7 qdd, Vect6 ex_fn, Vect7 ret_tau);
FX_BOOL  FX_Robot_Dyna_MOI_Mat_Fix(FX_INT32L RobotSerial, Matrix7 ret_MOImat);
FX_BOOL  FX_Robot_Dyna_Centri_Base_Fix(FX_INT32L RobotSerial, Matrix7 ret_CentriBase);
FX_BOOL  FX_Robot_Dyna_Centri_Mat_Fix(FX_INT32L RobotSerial, Matrix7 in_CentriBase, Vect7 in_AngVel, Matrix7 ret_CentriMat);
FX_BOOL  FX_Robot_Dyna_Coriolis_Base_Fix(FX_INT32L RobotSerial, Matrix7 ret_ColiosBase[7]);
FX_BOOL  FX_Robot_Dyna_Coriolis_Mat_Fix(FX_INT32L RobotSerial, Matrix7 in_ColiosBase[7], Vect7 in_AngVel, Matrix7 ret_ColiosMat);
/*/
in_BaseGes    ROBOT BASE CORD IN OUTSIDE CORD
in_BaseAcc    BASE ACC IN ROBOT CORD
in_BaseOmg    BASE ROT VEL IN ROBOT CORD
in_BaseOmgD   BASE ROT ACC IN ROBOT CORD
/*/
FX_BOOL  FX_Robot_Dyna_Flt_BaseSet(FX_INT32L RobotSerial, Matrix3 in_BaseGes, Vect3 in_BaseAcc,Vect3 in_BaseOmg, Vect3 in_BaseOmgD);

FX_BOOL  FX_Robot_Dyna_Centri_Base_Flt(FX_INT32L RobotSerial, Matrix8 ret_CentriBase);
FX_BOOL  FX_Robot_Dyna_Centri_Mat_Flt(FX_INT32L RobotSerial, Matrix8 in_CentriBase, Vect7 in_AngVel, Matrix7 ret_CentriMat);

FX_BOOL  FX_Robot_Dyna_Coriolis_Base_Flt(FX_INT32L RobotSerial, Matrix8 ret_ColiosBase[8]);
FX_BOOL  FX_Robot_Dyna_Coriolis_Mat_Flt(FX_INT32L RobotSerial, Matrix8 in_ColiosBase[8], Vect7 in_AngVel, Matrix8 ret_ColiosMat);




FX_BOOL  FX_Robot_Dyna_ID_Folt(FX_INT32L RobotSerial, Vect7 q, Vect7 qd, Vect7 qdd,Vect3 base_omg,Vect3 base_omgd,Vect3 base_grv, Vect6 ex_fn,Vect7 ret_tau);
FX_BOOL  FX_Robot_Dyna_Map_DynPara_B2A(PosGes A, PosGes B, Matrix3 I_in_b, Vect3 Mcp_in_b, Matrix3 ret_I_in_a, Vect3 ret_Mcp_in_a);



#endif
