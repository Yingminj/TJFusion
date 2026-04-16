#include "FxRobot.h"
#include "FXMatrix.h"
#include <Eigen/Geometry>
#ifdef _USER_IF_TAG_
#include "stdio.h"
#include "stdlib.h"
FX_BOOL  LOADMvCfg(FX_CHAR* path, FX_INT32L TYPE[2], FX_DOUBLE GRV[2][3], FX_DOUBLE DH[2][8][4], FX_DOUBLE PNVA[2][7][4], FX_DOUBLE BD[2][4][3],
	FX_DOUBLE Mass[2][7], FX_DOUBLE MCP[2][7][3], FX_DOUBLE I[2][7][6])
{
	FILE* fp = fopen(path, "rb");
	if (fp == NULL)
	{
		return FX_FALSE;
	}
	FX_INT32L i;
	FX_INT32L j;
	FX_CHAR   c;
	for ( i = 0; i < 2; i++)
	{
		if (fscanf(fp, "%ld,%lf,%lf,%lf,%c", &TYPE[i], &GRV[i][0], &GRV[i][1], &GRV[i][2], &c) != 5)
		{
			fclose(fp);
			return FX_FALSE;
		}
		if (c != 0x0a)
		{
			fclose(fp);
			return FX_FALSE;
		}

		for ( j = 0; j < 7; j++)
		{
			if (fscanf(fp, "%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%c", 
				&DH[i][j][0], &DH[i][j][1], &DH[i][j][2], &DH[i][j][3],
				&PNVA[i][j][1], &PNVA[i][j][0], &PNVA[i][j][2], &PNVA[i][j][3],
				&Mass[i][j], &MCP[i][j][0], &MCP[i][j][1], &MCP[i][j][2],
				&I[i][j][0], &I[i][j][1], &I[i][j][2], &I[i][j][3], &I[i][j][4], &I[i][j][5],
				&c) != 19)
			{
				fclose(fp);
				return FX_FALSE;
			}
			if (c != 0x0a)
			{
				fclose(fp);
				return FX_FALSE;
			}
		}

		if (fscanf(fp, "%lf,%lf,%lf,%lf,%c",&DH[i][7][0], &DH[i][7][1], &DH[i][7][2], &DH[i][7][3],
			&c) != 5)
		{
			fclose(fp);
			return FX_FALSE;
		}
		if (c != 0x0a)
		{
			fclose(fp);
			return FX_FALSE;
		}

		for (j = 0; j < 4; j++)
		{
			if (fscanf(fp, "%lf,%lf,%lf,%c",
				 &BD[i][j][0], &BD[i][j][1], &BD[i][j][2],&c) != 4)
			{
				fclose(fp);
				return FX_FALSE;
			}
			if (c != 0x0a)
			{
				fclose(fp);
				return FX_FALSE;
			}
		}
	}

	fclose(fp);
	return FX_TRUE;
}
#endif



FX_Robot			m_Robot[MAX_RUN_ROBOT_NUM];
FX_KineSPC_Pilot	m_Robot_SPC_Pilot[MAX_RUN_ROBOT_NUM];
FX_KineSPC_DL       m_Robot_SPC_DL[MAX_RUN_ROBOT_NUM];

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
FX_BOOL  FX_Robot_Init_Type(FX_INT32L RobotSerial, FX_INT32L RobotType)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	if (RobotType == FX_ROBOT_TYPE_DL)
	{
		m_Robot[RobotSerial].m_RobotType = FX_ROBOT_TYPE_DL;
		m_Robot[RobotSerial].m_RobotDOF = 6;
		m_Robot[RobotSerial].m_KineSPC = (FX_VOID*)&(m_Robot_SPC_DL[RobotSerial]);
		return FX_TRUE;
	}
	else if (RobotType == FX_ROBOT_TYPE_PILOT_SRS)
	{
		m_Robot[RobotSerial].m_RobotType = FX_ROBOT_TYPE_PILOT_SRS;
		m_Robot[RobotSerial].m_RobotDOF = 7;
		m_Robot[RobotSerial].m_KineSPC = (FX_VOID*)&(m_Robot_SPC_Pilot[RobotSerial]);
		m_Robot_SPC_Pilot[RobotSerial].m_IsCross = FX_FALSE;
		m_Robot_SPC_Pilot[RobotSerial].m_nsp.m_IsCorss = FX_FALSE;
		return FX_TRUE;
	}
	else if (RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		m_Robot[RobotSerial].m_RobotType = FX_ROBOT_TYPE_PILOT_CCS;
		m_Robot[RobotSerial].m_KineSPC = (FX_VOID*)&(m_Robot_SPC_Pilot[RobotSerial]);
		m_Robot_SPC_Pilot[RobotSerial].m_IsCross = FX_TRUE;
		m_Robot_SPC_Pilot[RobotSerial].m_nsp.m_IsCorss = FX_TRUE;
		return FX_TRUE;
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}


////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_BOOL  FX_Init_Robot_Kine_DL(FX_INT32L RobotSerial, FX_DOUBLE DH[8][4])
{
	return FX_FALSE;
}

FX_BOOL  FX_Init_Robot_Kine_Pilot_SRS(FX_INT32L RobotSerial, FX_DOUBLE DH[8][4])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	SPC->m_IsCross = FX_FALSE;
	FX_INT32 i;
	for (i = 0; i < 7; i++) {
		FX_IdentM44(pRobot->m_KineBase.m_AxisRotBase[i]);
		FX_IdentM44(pRobot->m_KineBase.m_JointPG[i]);
		FX_IdentM44(pRobot->m_KineBase.m_AxisRotTip[i]);
	}

	FX_IdentM44(pRobot->m_KineBase.m_Flange);
	FX_IdentM44(pRobot->m_KineBase.m_InvFlange);
	FX_IdentM44(pRobot->m_KineBase.m_Tool);
	FX_IdentM44(pRobot->m_KineBase.m_InvTool);
	FX_IdentM44(pRobot->m_KineBase.m_TCP);

	FX_DOUBLE L1 = DH[0][2];
	FX_DOUBLE L2 = DH[2][2];
	FX_DOUBLE L3 = DH[4][2];
	FX_DOUBLE D = DH[3][1];
	FX_DOUBLE Flan = DH[7][2];

	pRobot->m_KineBase.m_AxisRotBase[0][2][3] = L1;

	pRobot->m_KineBase.m_AxisRotBase[1][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[1][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[1][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[1][2][2] = 0;

	pRobot->m_KineBase.m_AxisRotBase[2][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[2][1][2] = 1;
	pRobot->m_KineBase.m_AxisRotBase[2][2][1] = -1; pRobot->m_KineBase.m_AxisRotBase[2][2][2] = 0;

	pRobot->m_KineBase.m_AxisRotBase[3][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[3][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[3][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[3][2][2] = 0;
	pRobot->m_KineBase.m_AxisRotBase[3][0][3] = D;
	pRobot->m_KineBase.m_AxisRotBase[3][2][3] = L2;

	pRobot->m_KineBase.m_AxisRotBase[4][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[4][1][2] = 1;
	pRobot->m_KineBase.m_AxisRotBase[4][2][1] = -1; pRobot->m_KineBase.m_AxisRotBase[4][2][2] = 0;
	pRobot->m_KineBase.m_AxisRotBase[4][0][3] = -D;
	pRobot->m_KineBase.m_AxisRotBase[4][1][3] = L3;

	pRobot->m_KineBase.m_AxisRotBase[5][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[5][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[5][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[5][2][2] = 0;

	{
		pRobot->m_KineBase.m_AxisRotBase[6][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[6][1][2] = 1;
		pRobot->m_KineBase.m_AxisRotBase[6][2][1] = -1; pRobot->m_KineBase.m_AxisRotBase[6][2][2] = 0;
		pRobot->m_KineBase.m_Flange[2][3] = Flan;
		FX_PGMatrixInv(pRobot->m_KineBase.m_Flange, pRobot->m_KineBase.m_InvFlange);
	}


	// Inverse Kinematics
	SPC->L1 = FX_Sqrt(L2 * L2 + D * D);
	SPC->L2 = FX_Sqrt(L3 * L3 + D * D);
	// initial angle of t4
	SPC->Ang1 = FX_ATan2(D, L2) * FXARM_R2D;
	SPC->Ang2 = FX_ATan2(D, L3) * FXARM_R2D;
	SPC->Angt = 180.0 - SPC->Ang1 - SPC->Ang2;
	SPC->m_J4_Bound = -SPC->Ang1;

	SPC->cart_len = FX_Sqrt(SPC->L1 * SPC->L1 + SPC->L2 * SPC->L2);

	FX_DOUBLE PV[7] = { 0 };
	FX_DOUBLE PG[4][4] = { 0 };

	return FX_TRUE;
}
FX_BOOL  FX_Init_Robot_Kine_Pilot_CCS(FX_INT32L RobotSerial, FX_DOUBLE DH[8][4])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	SPC->m_IsCross = FX_TRUE;
	FX_INT32 i;
	for (i = 0; i < 7; i++) {
		FX_IdentM44(pRobot->m_KineBase.m_AxisRotBase[i]);
		FX_IdentM44(pRobot->m_KineBase.m_JointPG[i]);
		FX_IdentM44(pRobot->m_KineBase.m_AxisRotTip[i]);
	}

	FX_IdentM44(pRobot->m_KineBase.m_Flange);
	FX_IdentM44(pRobot->m_KineBase.m_InvFlange);
	FX_IdentM44(pRobot->m_KineBase.m_Tool);
	FX_IdentM44(pRobot->m_KineBase.m_InvTool);
	FX_IdentM44(pRobot->m_KineBase.m_TCP);

	FX_DOUBLE L1 = DH[0][2];
	FX_DOUBLE L2 = DH[2][2];
	FX_DOUBLE L3 = DH[4][2];
	FX_DOUBLE D = DH[3][1];
	FX_DOUBLE Flan = DH[7][2];

	pRobot->m_KineBase.m_AxisRotBase[0][2][3] = L1;

	pRobot->m_KineBase.m_AxisRotBase[1][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[1][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[1][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[1][2][2] = 0;

	pRobot->m_KineBase.m_AxisRotBase[2][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[2][1][2] = 1;
	pRobot->m_KineBase.m_AxisRotBase[2][2][1] = -1; pRobot->m_KineBase.m_AxisRotBase[2][2][2] = 0;

	pRobot->m_KineBase.m_AxisRotBase[3][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[3][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[3][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[3][2][2] = 0;
	pRobot->m_KineBase.m_AxisRotBase[3][0][3] = D;
	pRobot->m_KineBase.m_AxisRotBase[3][2][3] = L2;

	pRobot->m_KineBase.m_AxisRotBase[4][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[4][1][2] = 1;
	pRobot->m_KineBase.m_AxisRotBase[4][2][1] = -1; pRobot->m_KineBase.m_AxisRotBase[4][2][2] = 0;
	pRobot->m_KineBase.m_AxisRotBase[4][0][3] = -D;
	pRobot->m_KineBase.m_AxisRotBase[4][1][3] = L3;

	pRobot->m_KineBase.m_AxisRotBase[5][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[5][1][2] = -1;
	pRobot->m_KineBase.m_AxisRotBase[5][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[5][2][2] = 0;

	{
		pRobot->m_KineBase.m_AxisRotBase[6][0][0] = 0; pRobot->m_KineBase.m_AxisRotBase[6][0][1] = 0; pRobot->m_KineBase.m_AxisRotBase[6][0][2] = 1;
		pRobot->m_KineBase.m_AxisRotBase[6][1][0] = 1; pRobot->m_KineBase.m_AxisRotBase[6][1][1] = 0; pRobot->m_KineBase.m_AxisRotBase[6][1][2] = 0;
		pRobot->m_KineBase.m_AxisRotBase[6][2][0] = 0; pRobot->m_KineBase.m_AxisRotBase[6][2][1] = 1; pRobot->m_KineBase.m_AxisRotBase[6][2][2] = 0;

		pRobot->m_KineBase.m_Flange[0][0] = 0; pRobot->m_KineBase.m_Flange[0][1] = 0;  pRobot->m_KineBase.m_Flange[0][2] = 1; pRobot->m_KineBase.m_Flange[0][3] = Flan;
		pRobot->m_KineBase.m_Flange[1][0] = 0; pRobot->m_KineBase.m_Flange[1][1] = -1; pRobot->m_KineBase.m_Flange[1][2] = 0;
		pRobot->m_KineBase.m_Flange[2][0] = 1; pRobot->m_KineBase.m_Flange[2][1] = 0;  pRobot->m_KineBase.m_Flange[2][2] = 0;

		FX_PGMatrixInv(pRobot->m_KineBase.m_Flange, pRobot->m_KineBase.m_InvFlange);
	}


	// Inverse Kinematics
	SPC->L1 = FX_Sqrt(L2 * L2 + D * D);
	SPC->L2 = FX_Sqrt(L3 * L3 + D * D);
	// initial angle of t4
	SPC->Ang1 = FX_ATan2(D, L2) * FXARM_R2D;
	SPC->Ang2 = FX_ATan2(D, L3) * FXARM_R2D;
	SPC->Angt = 180.0 - SPC->Ang1 - SPC->Ang2;
	SPC->m_J4_Bound = -SPC->Ang1;

	SPC->cart_len = FX_Sqrt(SPC->L1 * SPC->L1 + SPC->L2 * SPC->L2);

	FX_DOUBLE PV[7] = { 0 };
	FX_DOUBLE PG[4][4] = { 0 };

	return FX_TRUE;
}



FX_BOOL  FX_Robot_Init_Kine(FX_INT32L RobotSerial, FX_DOUBLE DH[8][4])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		FX_INT32L i;

		for ( i = 0; i < 7; i++)
		{
			pRobot->m_RobotDH[i][0] = DH[i][0];
			pRobot->m_RobotDH[i][1] = DH[i][1];
			pRobot->m_RobotDH[i][2] = DH[i][2];
			pRobot->m_RobotDH[i][3] = DH[i][3];

		}
		if (FX_Init_Robot_Kine_DL(RobotSerial, DH) == FX_FALSE)
		{
			return FX_FALSE;
		}
		pRobot->m_RobotDOF = 6;
		FX_DOUBLE jv[7] = {0};
		Matrix4  pg;
		FX_Robot_Kine_FK(RobotSerial,jv,pg);
		return FX_TRUE;
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS)
	{
		FX_INT32L i;
		for (i = 0; i < 8; i++)
		{
			pRobot->m_RobotDH[i][0] = DH[i][0];
			pRobot->m_RobotDH[i][1] = DH[i][1];
			pRobot->m_RobotDH[i][2] = DH[i][2];
			pRobot->m_RobotDH[i][3] = DH[i][3];
		}
		if (FX_Init_Robot_Kine_Pilot_SRS(RobotSerial, DH) == FX_FALSE)
		{
			return FX_FALSE;
		}
		pRobot->m_RobotDOF = 7;
		FX_DOUBLE jv[7] = { 0 };
		Matrix4  pg;
		FX_Robot_Kine_FK(RobotSerial, jv, pg);
		return FX_TRUE;
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		FX_INT32L i;
		for (i = 0; i < 8; i++)
		{
			pRobot->m_RobotDH[i][0] = DH[i][0];
			pRobot->m_RobotDH[i][1] = DH[i][1];
			pRobot->m_RobotDH[i][2] = DH[i][2];
			pRobot->m_RobotDH[i][3] = DH[i][3];
		}
		if (FX_Init_Robot_Kine_Pilot_CCS(RobotSerial, DH) == FX_FALSE)
		{
			return FX_FALSE;
		}
		pRobot->m_RobotDOF = 7;
		FX_DOUBLE jv[7] = { 0 };
		Matrix4  pg;
		FX_Robot_Kine_FK(RobotSerial, jv, pg);
		return FX_TRUE;
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}


////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_BOOL  FX_Init_Robot_Lmt_DL(FX_INT32L RobotSerial, FX_DOUBLE PNVA[7][4])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_INT32L i;
	for ( i = 0; i < pRobot->m_RobotDOF; i++)
	{
		pRobot->m_Lmt.m_JLmtPos_P[i] = PNVA[i][0];
		pRobot->m_Lmt.m_JLmtPos_N[i] = PNVA[i][1];
		pRobot->m_Lmt.m_JLmtVel[i] = PNVA[i][2];
		pRobot->m_Lmt.m_JLmtAcc[i] = PNVA[i][3];
	}
	return FX_TRUE;
}

FX_BOOL  FX_Init_Robot_Lmt_SRS(FX_INT32L RobotSerial, FX_DOUBLE PNVA[7][4])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_INT32L i;
	for (i = 0; i < pRobot->m_RobotDOF; i++)
	{
		pRobot->m_Lmt.m_JLmtPos_P[i] = PNVA[i][0];
		pRobot->m_Lmt.m_JLmtPos_N[i] = PNVA[i][1];
		pRobot->m_Lmt.m_JLmtVel[i] = PNVA[i][2];
		pRobot->m_Lmt.m_JLmtAcc[i] = PNVA[i][3];
	}
	return FX_TRUE;
}


FX_BOOL  FX_Init_Robot_Lmt_CCS(FX_INT32L RobotSerial, FX_DOUBLE PNVA[7][4], FX_DOUBLE J67[4][3])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_INT32L i;
	for (i = 0; i < pRobot->m_RobotDOF; i++)
	{
		pRobot->m_Lmt.m_JLmtPos_P[i] = PNVA[i][0];
		pRobot->m_Lmt.m_JLmtPos_N[i] = PNVA[i][1];
		pRobot->m_Lmt.m_JLmtVel[i] = PNVA[i][2];
		pRobot->m_Lmt.m_JLmtAcc[i] = PNVA[i][3];
	}

	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);

	for (i = 0; i < 3; i++)
	{
		SPC->lmtj67_pp[i] = J67[0][i];
		SPC->lmtj67_np[i] = J67[1][i];
		SPC->lmtj67_nn[i] = J67[2][i];
		SPC->lmtj67_pn[i] = J67[3][i];
	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Init_Lmt(FX_INT32L RobotSerial, FX_DOUBLE PNVA[7][4], FX_DOUBLE J67[4][3])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		return FX_Init_Robot_Lmt_DL(RobotSerial, PNVA);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS)
	{
		return FX_Init_Robot_Lmt_SRS(RobotSerial, PNVA);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		return FX_Init_Robot_Lmt_CCS(RobotSerial, PNVA, J67);
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


FX_VOID FX_XYZMRot(FX_DOUBLE L[4][4], FX_DOUBLE cosv, FX_DOUBLE sinv, FX_DOUBLE T[4][4])
{
	FX_INT32L i;
	for (i = 0; i < 3; i++)
	{
		T[i][0] = L[i][0] * cosv + L[i][1] * sinv;
		T[i][1] = -L[i][0] * sinv + L[i][1] * cosv;
		T[i][2] = L[i][2];
		T[i][3] = L[i][3];
	}
	T[3][0] = 0;
	T[3][1] = 0;
	T[3][2] = 0;
	T[3][3] = 1;
}


FX_BOOL  FX_Robot_Kine_Piolt(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE pgos[4][4])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	long i;
	FX_DOUBLE cosv, sinv;
	for (i = 0; i < 7; i++)
	{
		FX_SIN_COS_DEG(joints[i], &sinv, &cosv);
		FX_XYZMRot(pRobot->m_KineBase.m_AxisRotBase[i], cosv, sinv, pRobot->m_KineBase.m_AxisRotTip[i]);
	}

	FX_M44Copy(pRobot->m_KineBase.m_AxisRotTip[0], pRobot->m_KineBase.m_JointPG[0]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[0], pRobot->m_KineBase.m_AxisRotTip[1], pRobot->m_KineBase.m_JointPG[1]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[1], pRobot->m_KineBase.m_AxisRotTip[2], pRobot->m_KineBase.m_JointPG[2]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[2], pRobot->m_KineBase.m_AxisRotTip[3], pRobot->m_KineBase.m_JointPG[3]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[3], pRobot->m_KineBase.m_AxisRotTip[4], pRobot->m_KineBase.m_JointPG[4]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[4], pRobot->m_KineBase.m_AxisRotTip[5], pRobot->m_KineBase.m_JointPG[5]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[5], pRobot->m_KineBase.m_AxisRotTip[6], pRobot->m_KineBase.m_JointPG[6]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[6], pRobot->m_KineBase.m_Flange, pRobot->m_KineBase.m_FlangeTip);
	FX_PGMult(pRobot->m_KineBase.m_FlangeTip, pRobot->m_KineBase.m_Tool, pRobot->m_KineBase.m_TCP);
	FX_M44Copy(pRobot->m_KineBase.m_TCP, pgos);
	return FX_TRUE;
}



FX_BOOL  FX_Robot_Kine_DL(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE pgos[4][4])
{

	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	long i;
	FX_DOUBLE cosv, sinv;
	for (i = 0; i < 6; i++)
	{
		FX_SIN_COS_DEG(joints[i], &sinv, &cosv);
		FX_XYZMRot(pRobot->m_KineBase.m_AxisRotBase[i], cosv, sinv, pRobot->m_KineBase.m_AxisRotTip[i]);
	}

	FX_M44Copy(pRobot->m_KineBase.m_AxisRotTip[0], pRobot->m_KineBase.m_JointPG[0]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[0], pRobot->m_KineBase.m_AxisRotTip[1], pRobot->m_KineBase.m_JointPG[1]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[1], pRobot->m_KineBase.m_AxisRotTip[2], pRobot->m_KineBase.m_JointPG[2]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[2], pRobot->m_KineBase.m_AxisRotTip[3], pRobot->m_KineBase.m_JointPG[3]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[3], pRobot->m_KineBase.m_AxisRotTip[4], pRobot->m_KineBase.m_JointPG[4]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[4], pRobot->m_KineBase.m_AxisRotTip[5], pRobot->m_KineBase.m_JointPG[5]);
	FX_PGMult(pRobot->m_KineBase.m_JointPG[5], pRobot->m_KineBase.m_Flange, pRobot->m_KineBase.m_FlangeTip);
	FX_PGMult(pRobot->m_KineBase.m_FlangeTip, pRobot->m_KineBase.m_Tool, pRobot->m_KineBase.m_TCP);
	FX_M44Copy(pRobot->m_KineBase.m_TCP, pgos);
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Tool_Set(FX_INT32L RobotSerial, Matrix4 tool)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	FX_INT32 i;
	FX_INT32 j;
	for (i = 0; i < 3; i++)
	{
		for (j = 0; j < 4; j++)
		{
			pRobot->m_KineBase.m_Tool[i][j] = tool[i][j];
		}
	}
	pRobot->m_KineBase.m_Tool[3][0] = 0;
	pRobot->m_KineBase.m_Tool[3][1] = 0;
	pRobot->m_KineBase.m_Tool[3][2] = 0;
	pRobot->m_KineBase.m_Tool[3][3] = 1;
	FX_PGMatrixInv(pRobot->m_KineBase.m_Tool, pRobot->m_KineBase.m_InvTool);
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Tool_Rmv(FX_INT32L RobotSerial)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	FX_IdentM44(pRobot->m_KineBase.m_Tool);
	FX_IdentM44(pRobot->m_KineBase.m_InvTool);
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Kine_FK(FX_INT32L RobotSerial, FX_DOUBLE joints[7], Matrix4 pgos)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		return FX_Robot_Kine_DL(RobotSerial, joints, pgos);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS)
	{
		return FX_Robot_Kine_Piolt(RobotSerial, joints, pgos);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		return FX_Robot_Kine_Piolt(RobotSerial, joints, pgos);
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_BOOL  FX_Jacb_ROT_7(FX_INT32L RobotSerial, FX_DOUBLE jcb[6][7])
{
	FX_INT32 i;
	FX_DOUBLE Vm[3];
	FX_DOUBLE Vr[3];
	FX_DOUBLE V[3];
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	for (i = 0; i < 7; i++)
	{
		Vm[0] = pRobot->m_KineBase.m_TCP[0][3] - pRobot->m_KineBase.m_JointPG[i][0][3];
		Vm[1] = pRobot->m_KineBase.m_TCP[1][3] - pRobot->m_KineBase.m_JointPG[i][1][3];
		Vm[2] = pRobot->m_KineBase.m_TCP[2][3] - pRobot->m_KineBase.m_JointPG[i][2][3];

		Vr[0] = pRobot->m_KineBase.m_JointPG[i][0][2];
		Vr[1] = pRobot->m_KineBase.m_JointPG[i][1][2];
		Vr[2] = pRobot->m_KineBase.m_JointPG[i][2][2];

		FX_VectCross(Vr, Vm, V);

		jcb[0][i] = V[0] * 0.001;
		jcb[1][i] = V[1] * 0.001;
		jcb[2][i] = V[2] * 0.001;
		jcb[3][i] = Vr[0];
		jcb[4][i] = Vr[1];
		jcb[5][i] = Vr[2];
	}	
	return FX_TRUE;
}


FX_BOOL  FX_Jacb_ROT_6(FX_INT32L RobotSerial, FX_DOUBLE jcb[6][6])
{
	FX_INT32 i;
	FX_DOUBLE Vm[3];
	FX_DOUBLE Vr[3];
	FX_DOUBLE V[3];
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	for (i = 0; i < 6; i++)
	{
		Vm[0] = pRobot->m_KineBase.m_TCP[0][3] - pRobot->m_KineBase.m_JointPG[i][0][3];
		Vm[1] = pRobot->m_KineBase.m_TCP[1][3] - pRobot->m_KineBase.m_JointPG[i][1][3];
		Vm[2] = pRobot->m_KineBase.m_TCP[2][3] - pRobot->m_KineBase.m_JointPG[i][2][3];

		Vr[0] = pRobot->m_KineBase.m_JointPG[i][0][2];
		Vr[1] = pRobot->m_KineBase.m_JointPG[i][1][2];
		Vr[2] = pRobot->m_KineBase.m_JointPG[i][2][2];

		FX_VectCross(Vr, Vm, V);

		jcb[0][i] = V[0] * 0.001;
		jcb[1][i] = V[1] * 0.001;
		jcb[2][i] = V[2] * 0.001;
		jcb[3][i] = Vr[0];
		jcb[4][i] = Vr[1];
		jcb[5][i] = Vr[2];
	}
	return FX_TRUE;
}

FX_BOOL  FX_JacbAxis7(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE jcb[6][7])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial]; 
	
	if (	pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS 
		||  pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		Matrix4 pg;
		if (FX_Robot_Kine_FK(RobotSerial, joints, pg) == FX_FALSE)
		{
			return FX_FALSE;
		}
		return FX_Jacb_ROT_7(RobotSerial, jcb);
	}
	
	return FX_FALSE;
}


FX_BOOL  FX_JacbAixs6(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE jcb[6][6])
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		Matrix4 pg;
		if (FX_Robot_Kine_FK(RobotSerial, joints, pg) == FX_FALSE)
		{
			return FX_FALSE;
		}
		return FX_Jacb_ROT_6(RobotSerial, jcb);
	}
	return FX_FALSE;
}

FX_BOOL  FX_Robot_Kine_Jacb(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_Jacobi *jcb)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS
		|| pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		jcb->m_AxisNum = 7;
		return FX_JacbAxis7(RobotSerial, joints, jcb->m_Jcb);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		FX_DOUBLE tmp_jcb[6][6];
		jcb->m_AxisNum = 6;
		if (FX_JacbAixs6(RobotSerial, joints, tmp_jcb) == FX_FALSE)
		{
			return FX_FALSE;
		}
		FX_INT32L i, j;
		for ( i = 0; i < 6; i++)
		{
			for (j = 0; j < 6; j++) 
			{
				jcb->m_Jcb[i][j] = tmp_jcb[i][j];
			}
			jcb->m_Jcb[i][6] = 0;
		}
		return FX_TRUE;
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}


////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


FX_BOOL  FX_Jacb_Dot_ROT_7(FX_INT32L RobotSerial, FX_DOUBLE jvel[7], FX_DOUBLE jcb_dot[6][7])
{
	FX_INT32 i;
	FX_INT32 dof = 7;
	FX_DOUBLE e[8][3] = { 0 };
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	for (i = 0; i < dof; i++)
	{
		e[i][0] = pRobot->m_KineBase.m_JointPG[i][0][2];
		e[i][1] = pRobot->m_KineBase.m_JointPG[i][1][2];
		e[i][2] = pRobot->m_KineBase.m_JointPG[i][2][2];
	}

	FX_DOUBLE w[8][3] = { 0 };
	w[0][0] = e[0][0] * jvel[0] * FXARM_D2R;
	w[0][1] = e[0][1] * jvel[0] * FXARM_D2R;
	w[0][2] = e[0][2] * jvel[0] * FXARM_D2R;

	for (i = 1; i < dof; i++)
	{
		w[i][0] = w[i - 1][0] + e[i][0] * jvel[i] * FXARM_D2R;
		w[i][1] = w[i - 1][1] + e[i][1] * jvel[i] * FXARM_D2R;
		w[i][2] = w[i - 1][2] + e[i][2] * jvel[i] * FXARM_D2R;
	}

	FX_DOUBLE ed[8][3] = { 0 };
	for (i = 0; i < dof; i++)
	{
		FX_VectCross(w[i], e[i], ed[i]);
	}

	FX_DOUBLE p[8][3] = { 0 };
	for (i = 0; i < dof - 1; i++)
	{
		p[i][0] = (pRobot->m_KineBase.m_JointPG[i + 1][0][3] - pRobot->m_KineBase.m_JointPG[i][0][3]) * 0.001;
		p[i][1] = (pRobot->m_KineBase.m_JointPG[i + 1][1][3] - pRobot->m_KineBase.m_JointPG[i][1][3]) * 0.001;
		p[i][2] = (pRobot->m_KineBase.m_JointPG[i + 1][2][3] - pRobot->m_KineBase.m_JointPG[i][2][3]) * 0.001;
	}

	p[dof - 1][0] = (pRobot->m_KineBase.m_TCP[0][3] - pRobot->m_KineBase.m_JointPG[dof - 1][0][3]) * 0.001;
	p[dof - 1][1] = (pRobot->m_KineBase.m_TCP[1][3] - pRobot->m_KineBase.m_JointPG[dof - 1][1][3]) * 0.001;
	p[dof - 1][2] = (pRobot->m_KineBase.m_TCP[2][3] - pRobot->m_KineBase.m_JointPG[dof - 1][2][3]) * 0.001;

	FX_DOUBLE pd[8][3] = { 0 };

	FX_VectCross(p[dof - 1], w[dof - 1], pd[dof - 1]);
	for (i = dof - 2; i >= 0; i--)
	{
		FX_VectCross(p[i], w[i], pd[i]);
		pd[i][0] += pd[i + 1][0];
		pd[i][1] += pd[i + 1][1];
		pd[i][2] += pd[i + 1][2];
	}

	FX_DOUBLE v3tmp1[3] = { 0 };
	FX_DOUBLE v3tmp2[3] = { 0 };

	for (i = 0; i < dof; i++)
	{
		FX_VectCross(pd[i], e[i], v3tmp1);
		FX_VectCross(p[i], ed[i], v3tmp2);

		jcb_dot[0][i] = (v3tmp1[0] + v3tmp2[0]);
		jcb_dot[1][i] = (v3tmp1[1] + v3tmp2[1]);
		jcb_dot[2][i] = (v3tmp1[2] + v3tmp2[2]);

		jcb_dot[3][i] = ed[i][0];
		jcb_dot[4][i] = ed[i][1];
		jcb_dot[5][i] = ed[i][2];
	}

	return FX_TRUE;
}


FX_BOOL  FX_Jacb_Dot_ROT_6(FX_INT32L RobotSerial, FX_DOUBLE jvel[7], FX_DOUBLE jcb_dot[6][6])
{
	FX_INT32 i;
	FX_INT32 dof = 6;
	FX_DOUBLE e[8][3] = { 0 };
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	for (i = 0; i < dof; i++)
	{
		e[i][0] = pRobot->m_KineBase.m_JointPG[i][0][2];
		e[i][1] = pRobot->m_KineBase.m_JointPG[i][1][2];
		e[i][2] = pRobot->m_KineBase.m_JointPG[i][2][2];
	}

	FX_DOUBLE w[8][3] = { 0 };
	w[0][0] = e[0][0] * jvel[0] * FXARM_D2R;
	w[0][1] = e[0][1] * jvel[0] * FXARM_D2R;
	w[0][2] = e[0][2] * jvel[0] * FXARM_D2R;

	for (i = 1; i < dof; i++)
	{
		w[i][0] = w[i - 1][0] + e[i][0] * jvel[i] * FXARM_D2R;
		w[i][1] = w[i - 1][1] + e[i][1] * jvel[i] * FXARM_D2R;
		w[i][2] = w[i - 1][2] + e[i][2] * jvel[i] * FXARM_D2R;
	}

	FX_DOUBLE ed[8][3] = { 0 };
	for (i = 0; i < dof; i++)
	{
		FX_VectCross(w[i], e[i], ed[i]);
	}

	FX_DOUBLE p[8][3] = { 0 };
	for (i = 0; i < dof - 1; i++)
	{
		p[i][0] = (pRobot->m_KineBase.m_JointPG[i + 1][0][3] - pRobot->m_KineBase.m_JointPG[i][0][3]) * 0.001;
		p[i][1] = (pRobot->m_KineBase.m_JointPG[i + 1][1][3] - pRobot->m_KineBase.m_JointPG[i][1][3]) * 0.001;
		p[i][2] = (pRobot->m_KineBase.m_JointPG[i + 1][2][3] - pRobot->m_KineBase.m_JointPG[i][2][3]) * 0.001;
	}

	p[dof - 1][0] = (pRobot->m_KineBase.m_TCP[0][3] - pRobot->m_KineBase.m_JointPG[dof - 1][0][3]) * 0.001;
	p[dof - 1][1] = (pRobot->m_KineBase.m_TCP[1][3] - pRobot->m_KineBase.m_JointPG[dof - 1][1][3]) * 0.001;
	p[dof - 1][2] = (pRobot->m_KineBase.m_TCP[2][3] - pRobot->m_KineBase.m_JointPG[dof - 1][2][3]) * 0.001;

	FX_DOUBLE pd[8][3] = { 0 };

	FX_VectCross(p[dof - 1], w[dof - 1], pd[dof - 1]);
	for (i = dof - 2; i >= 0; i--)
	{
		FX_VectCross(p[i], w[i], pd[i]);
		pd[i][0] += pd[i + 1][0];
		pd[i][1] += pd[i + 1][1];
		pd[i][2] += pd[i + 1][2];
	}

	FX_DOUBLE v3tmp1[3] = { 0 };
	FX_DOUBLE v3tmp2[3] = { 0 };

	for (i = 0; i < dof; i++)
	{
		FX_VectCross(pd[i], e[i], v3tmp1);
		FX_VectCross(p[i], ed[i], v3tmp2);

		jcb_dot[0][i] = (v3tmp1[0] + v3tmp2[0]);
		jcb_dot[1][i] = (v3tmp1[1] + v3tmp2[1]);
		jcb_dot[2][i] = (v3tmp1[2] + v3tmp2[2]);

		jcb_dot[3][i] = ed[i][0];
		jcb_dot[4][i] = ed[i][1];
		jcb_dot[5][i] = ed[i][2];
	}
	return FX_TRUE;
}


FX_BOOL  FX_Robot_Kine_JacbJacbDot(FX_INT32L RobotSerial, FX_DOUBLE joints[7], FX_DOUBLE joints_vel[7], FX_Jacobi* jcb, FX_Jacobi* jcb_dot)
{

	if (FX_Robot_Kine_Jacb(RobotSerial, joints, jcb) == FX_FALSE)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS
		|| pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		jcb_dot->m_AxisNum = 7;
		return FX_Jacb_Dot_ROT_7(RobotSerial, joints_vel, jcb_dot->m_Jcb);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		FX_DOUBLE tmp_jcb[6][6];
		jcb_dot->m_AxisNum = 7;
		if (FX_Jacb_Dot_ROT_6(RobotSerial, joints_vel, tmp_jcb) == FX_FALSE)
		{
			return FX_FALSE;
		}
		FX_INT32L i, j;
		for (i = 0; i < 6; i++)
		{
			for (j = 0; j < 6; j++)
			{
				jcb_dot->m_Jcb[i][j] = tmp_jcb[i][j];
			}
			jcb_dot->m_Jcb[i][6] = 0;
		}
		return FX_TRUE;
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


FX_BOOL  FX_InvKine_DL(FX_INT32L RobotSerial, FX_InvKineSolvePara * solve_para)
{
	return FX_FALSE;
}


FX_INT32  FX_GetJ4Type_Pilot(FX_KineSPC_Pilot* SPC, FX_DOUBLE jv4)
{
	if (jv4 > SPC->m_J4_Bound + 0.00001)
	{
		return 1;
	}
	if (jv4 < SPC->m_J4_Bound - 0.00001)
	{
		return -1;
	}
	return 0;
}


FX_VOID  FX_SolveTrange2D(FX_DOUBLE x_pan, FX_DOUBLE r1x, FX_DOUBLE r1y, FX_DOUBLE r2x, FX_DOUBLE r2y, FX_DOUBLE ret_xy[2])
{
	FX_DOUBLE k1;
	FX_DOUBLE k2;

	if (FX_Fabs(r1x) < 0.00000001)
	{
		ret_xy[0] = 0;
		k2 = r2y / r2x;
		ret_xy[1] = -x_pan / k2;
		return;
	}

	if (FX_Fabs(r2x) < 0.00000001)
	{
		ret_xy[0] = x_pan;
		k1 = r1y / r1x;
		ret_xy[1] = x_pan / k1;
		return;
	}

	k1 = r1y / r1x;
	k2 = r2y / r2x;
	ret_xy[0] = -x_pan * k2 / (k1 - k2);
	ret_xy[1] = ret_xy[0] * k1;
	return;
}

FX_BOOL FX_SolveJ123ZNYZ(NSPBase* pnspbase, FX_DOUBLE rot_angle, FX_DOUBLE ref[7], FX_DOUBLE ret_j[7], FX_BOOL* is_degen)
{
	FX_DOUBLE m[3][3];
	FX_MatRotAxis(pnspbase->rot_axis, rot_angle, pnspbase->j123Base, m);

	FX_DOUBLE j[3];
	FX_DOUBLE j1[3];
	FX_DOUBLE j2[3];

	if (FX_Matrix2ZYZ(m, j) == FX_TRUE)
	{
		*is_degen = FX_FALSE;
		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[0], &j1[0])
			+ FX_MinDif_Circle(ref[1], &j1[1])
			+ FX_MinDif_Circle(ref[2], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[0], &j2[0])
			+ FX_MinDif_Circle(ref[1], &j2[1])
			+ FX_MinDif_Circle(ref[2], &j2[2]);

		if (err1 <= err2)
		{
			ret_j[0] = j1[0];
			ret_j[1] = j1[1];
			ret_j[2] = j1[2];
		}
		else
		{
			ret_j[0] = j2[0];
			ret_j[1] = j2[1];
			ret_j[2] = j2[2];
		}
		return FX_TRUE;
	}

	*is_degen = FX_TRUE;

	FX_DOUBLE jtmp1[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle + 1, pnspbase->j123Base, m);

		if (FX_Matrix2ZYZ(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[0], &j1[0])
			+ FX_MinDif_Circle(ref[1], &j1[1])
			+ FX_MinDif_Circle(ref[2], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[0], &j2[0])
			+ FX_MinDif_Circle(ref[1], &j2[1])
			+ FX_MinDif_Circle(ref[2], &j2[2]);

		if (err1 <= err2)
		{
			jtmp1[0] = j1[0];
			jtmp1[1] = j1[1];
			jtmp1[2] = j1[2];
		}
		else
		{
			jtmp1[0] = j2[0];
			jtmp1[1] = j2[1];
			jtmp1[2] = j2[2];

		}

	}



	FX_DOUBLE jtmp2[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle - 1, pnspbase->j123Base, m);

		if (FX_Matrix2ZYZ(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[0], &j1[0])
			+ FX_MinDif_Circle(ref[1], &j1[1])
			+ FX_MinDif_Circle(ref[2], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[0], &j2[0])
			+ FX_MinDif_Circle(ref[1], &j2[1])
			+ FX_MinDif_Circle(ref[2], &j2[2]);

		if (err1 <= err2)
		{
			jtmp2[0] = j1[0];
			jtmp2[1] = j1[1];
			jtmp2[2] = j1[2];
		}
		else
		{

			jtmp2[0] = j2[0];
			jtmp2[1] = j2[1];
			jtmp2[2] = j2[2];
		}

	}

	ret_j[0] = (jtmp1[0] + jtmp2[0]) * 0.5;
	ret_j[1] = (jtmp1[1] + jtmp2[2]) * 0.5;
	ret_j[2] = (jtmp1[2] + jtmp2[2]) * 0.5;

	return FX_TRUE;

}



FX_BOOL FX_SolveJ567ZNYZ(NSPBase* pnspbase, FX_DOUBLE rot_angle, FX_DOUBLE ref[7], FX_DOUBLE ret_j[7], FX_BOOL* is_degen)
{
	FX_DOUBLE m1[3][3];
	FX_DOUBLE m2[3][3];
	FX_DOUBLE m[3][3];
	FX_MatRotAxis(pnspbase->rot_axis, rot_angle, pnspbase->j567Base, m1);
	FX_M33Trans(m1, m2);

	FX_MMM33(m2, pnspbase->wristges, m);
	FX_DOUBLE j[3];
	FX_DOUBLE j1[3];
	FX_DOUBLE j2[3];

	if (FX_Matrix2ZYZ(m, j) == FX_TRUE)
	{
		*is_degen = FX_FALSE;
		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
			+ FX_MinDif_Circle(ref[5], &j1[1])
			+ FX_MinDif_Circle(ref[6], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
			+ FX_MinDif_Circle(ref[5], &j2[1])
			+ FX_MinDif_Circle(ref[6], &j2[2]);

		if (err1 <= err2)
		{
			ret_j[4] = j1[0];
			ret_j[5] = j1[1];
			ret_j[6] = j1[2];
		}
		else
		{
			ret_j[4] = j2[0];
			ret_j[5] = j2[1];
			ret_j[6] = j2[2];
		}
		return FX_TRUE;
	}

	*is_degen = FX_TRUE;

	FX_DOUBLE jtmp1[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle + 1, pnspbase->j567Base, m1);
		FX_M33Trans(m1, m2);

		FX_MMM33(m2, pnspbase->wristges, m);

		if (FX_Matrix2ZYZ(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
			+ FX_MinDif_Circle(ref[5], &j1[1])
			+ FX_MinDif_Circle(ref[6], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
			+ FX_MinDif_Circle(ref[5], &j2[1])
			+ FX_MinDif_Circle(ref[6], &j2[2]);

		if (err1 <= err2)
		{
			jtmp1[0] = j1[0];
			jtmp1[1] = j1[1];
			jtmp1[2] = j1[2];
		}
		else
		{
			jtmp1[0] = j2[0];
			jtmp1[1] = j2[1];
			jtmp1[2] = j2[2];
		}

	}



	FX_DOUBLE jtmp2[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle + 1, pnspbase->j567Base, m1);
		FX_M33Trans(m1, m2);

		FX_MMM33(m2, pnspbase->wristges, m);

		if (FX_Matrix2ZYZ(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];


		j2[0] = j[0] + 180;
		j2[1] = j[1];
		j2[2] = j[2] + 180;

		FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
			+ FX_MinDif_Circle(ref[5], &j1[1])
			+ FX_MinDif_Circle(ref[6], &j1[2]);
		FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
			+ FX_MinDif_Circle(ref[5], &j2[1])
			+ FX_MinDif_Circle(ref[6], &j2[2]);

		if (err1 <= err2)
		{
			jtmp2[0] = j1[0];
			jtmp2[1] = j1[1];
			jtmp2[2] = j1[2];
		}
		else
		{
			jtmp2[0] = j2[0];
			jtmp2[1] = j2[1];
			jtmp2[2] = j2[2];
		}


	}

	ret_j[4] = (jtmp1[0] + jtmp2[0]) * 0.5;
	ret_j[5] = (jtmp1[1] + jtmp2[2]) * 0.5;
	ret_j[6] = (jtmp1[2] + jtmp2[2]) * 0.5;

	return FX_TRUE;

}

FX_BOOL FX_SolveJ567ZNYX(NSPBase* pnspbase, FX_DOUBLE rot_angle, FX_DOUBLE ref[7], FX_DOUBLE ret_j[7], FX_BOOL* is_degen)
{
	FX_DOUBLE m1[3][3];
	FX_DOUBLE m2[3][3];
	FX_DOUBLE m[3][3];
	FX_MatRotAxis(pnspbase->rot_axis, rot_angle, pnspbase->j567Base, m1);
	FX_M33Trans(m1, m2);

	FX_MMM33(m2, pnspbase->wristges, m);
	FX_DOUBLE j[3];
	FX_DOUBLE j1[3];
	FX_DOUBLE j2[3];

	if (FX_Matrix2ZYX(m, j) == FX_TRUE)
	{
		*is_degen = FX_FALSE;
		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];

			ret_j[4] = j1[0];
			ret_j[5] = j1[1];
			ret_j[6] = j1[2];

		// j2[0] = j[0] + 180;
		// j2[1] = j[1];
		// j2[2] = j[2] + 180;

		// FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
		// 	+ FX_MinDif_Circle(ref[5], &j1[1])
		// 	+ FX_MinDif_Circle(ref[6], &j1[2]);
		// FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
		// 	+ FX_MinDif_Circle(ref[5], &j2[1])
		// 	+ FX_MinDif_Circle(ref[6], &j2[2]);

		// if (err1 <= err2)
		// {
		// 	ret_j[4] = j1[0];
		// 	ret_j[5] = j1[1];
		// 	ret_j[6] = j1[2];
		// }
		// else
		// {
		// 	ret_j[4] = j2[0];
		// 	ret_j[5] = j2[1];
		// 	ret_j[6] = j2[2];

		// }
		return FX_TRUE;
	}

	*is_degen = FX_TRUE;

	FX_DOUBLE jtmp1[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle + 1, pnspbase->j567Base, m1);
		FX_M33Trans(m1, m2);

		FX_MMM33(m2, pnspbase->wristges, m);

		if (FX_Matrix2ZYX(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];

 		jtmp1[0] = j1[0];
		jtmp1[1] = j1[1];
		jtmp1[2] = j1[2];

		// j2[0] = j[0] + 180;
		// j2[1] = j[1];
		// j2[2] = j[2] + 180;

		// FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
		// 	+ FX_MinDif_Circle(ref[5], &j1[1])
		// 	+ FX_MinDif_Circle(ref[6], &j1[2]);
		// FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
		// 	+ FX_MinDif_Circle(ref[5], &j2[1])
		// 	+ FX_MinDif_Circle(ref[6], &j2[2]);

		// if (err1 <= err2)
		// {
		// 	jtmp1[0] = j1[0];
		// 	jtmp1[1] = j1[1];
		// 	jtmp1[2] = j1[2];
		// }
		// else
		// {
		// 	jtmp1[0] = j2[0];
		// 	jtmp1[1] = j2[1];
		// 	jtmp1[2] = j2[2];
		// }


	}



	FX_DOUBLE jtmp2[3];
	{
		FX_MatRotAxis(pnspbase->rot_axis, rot_angle + 1, pnspbase->j567Base, m1);
		FX_M33Trans(m1, m2);

		FX_MMM33(m2, pnspbase->wristges, m);

		if (FX_Matrix2ZYX(m, j) == FX_FALSE)
		{
			return FX_FALSE;
		}

		j1[0] = j[0];
		j1[1] = -j[1];
		j1[2] = j[2];
		jtmp2[0] = j1[0];
		jtmp2[1] = j1[1];
		jtmp2[2] = j1[2];

		// j2[0] = j[0] + 180;
		// j2[1] = j[1];
		// j2[2] = j[2] + 180;

		// FX_DOUBLE err1 = FX_MinDif_Circle(ref[4], &j1[0])
		// 	+ FX_MinDif_Circle(ref[5], &j1[1])
		// 	+ FX_MinDif_Circle(ref[6], &j1[2]);
		// FX_DOUBLE err2 = FX_MinDif_Circle(ref[4], &j2[0])
		// 	+ FX_MinDif_Circle(ref[5], &j2[1])
		// 	+ FX_MinDif_Circle(ref[6], &j2[2]);

		// if (err1 <= err2)
		// {
		// 	jtmp2[0] = j1[0];
		// 	jtmp2[1] = j1[1];
		// 	jtmp2[2] = j1[2];
		// }
		// else
		// {
		// 	jtmp2[0] = j2[0];
		// 	jtmp2[1] = j2[1];
		// 	jtmp2[2] = j2[2];

		// }

	}

	ret_j[4] = (jtmp1[0] + jtmp2[0]) * 0.5;
	ret_j[5] = (jtmp1[1] + jtmp2[2]) * 0.5;
	ret_j[6] = (jtmp1[2] + jtmp2[2]) * 0.5;

	return FX_TRUE;

}


FX_BOOL  FX_InvKine_Pilot(FX_INT32L RobotSerial, FX_InvKineSolvePara * solve_para)
{
	FX_INT32L i;
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot * SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	NSPBase* NSP = &(SPC->m_nsp);
	solve_para->m_Output_IsOutRange = FX_FALSE;
	solve_para->m_Output_IsJntExd = FX_FALSE;
	solve_para->m_Input_ZSP_Angle = 0;
	for ( i = 0; i < 7; i++)
	{
		solve_para->m_Output_IsDeg[i] = FX_FALSE;
		solve_para->m_Output_JntExdTags[i] = FX_FALSE;
	}
	
	FX_DOUBLE m_flan[4][4];
	FX_DOUBLE m_wrist[4][4];
	FX_MMM44(solve_para->m_Input_IK_TargetTCP, pRobot->m_KineBase.m_InvTool, m_flan);
	FX_MMM44(m_flan, pRobot->m_KineBase.m_InvFlange, m_wrist);

	//// caculate point a (shoulder point) and point b (wrist point)
	FX_DOUBLE pa[3];
	FX_DOUBLE pb[3];

	pa[0] = pRobot->m_KineBase.m_JointPG[1][0][3];
	pa[1] = pRobot->m_KineBase.m_JointPG[1][1][3];
	pa[2] = pRobot->m_KineBase.m_JointPG[1][2][3];

	pb[0] = m_wrist[0][3];
	pb[1] = m_wrist[1][3];
	pb[2] = m_wrist[2][3];

	FX_DOUBLE  va2b[3];
	va2b[0] = pb[0] - pa[0];
	va2b[1] = pb[1] - pa[1];
	va2b[2] = pb[2] - pa[2];

	//// caculate j4 
	FX_DOUBLE ablen = FX_Sqrt(va2b[0] * va2b[0] + va2b[1] * va2b[1] + va2b[2] * va2b[2]);

	if (ablen + 0.1 >= SPC->L1 + SPC->L2)
	{
		solve_para->m_Output_IsOutRange = FX_TRUE;
		return FX_FALSE;
	}

	FX_DOUBLE t = SPC->L1 * SPC->L1 + SPC->L2 * SPC->L2 - ablen * ablen;
	FX_DOUBLE ang = FX_ACOS(t / (2.0 * SPC->L1 * SPC->L2)) * FXARM_R2D;
	FX_DOUBLE Jv3[2];
	Jv3[0] = SPC->Angt - ang;
	Jv3[1] = SPC->Angt + ang - 360;

	FX_INT32 j4type = FX_GetJ4Type_Pilot(SPC, solve_para->m_Input_IK_RefJoint[3]);
	if (j4type == 0)
	{
		solve_para->m_Output_IsOutRange = FX_TRUE;
		return FX_FALSE;
	}

	FX_INT32 j4type1 = FX_GetJ4Type_Pilot(SPC, Jv3[0]);
	FX_INT32 j4type2 = FX_GetJ4Type_Pilot(SPC, Jv3[1]);

	FX_DOUBLE JV4;

	if (j4type == j4type1)
	{
		JV4 = Jv3[0];
	}
	else if (j4type == j4type2)
	{
		JV4 = Jv3[1];
	}
	else
	{
		solve_para->m_Output_IsOutRange = FX_TRUE;
		return FX_FALSE;
	}


	/// caculate shoulder axis_cross_elbow wrist trangle
	FX_DOUBLE la = SPC->L1;
	FX_DOUBLE lb = SPC->L2;
	FX_DOUBLE lc = ablen;
	FX_DOUBLE t1 = lc * lc + la * la - lb * lb;
	FX_DOUBLE anga = FX_ACOS(t1 / (2.0 * lc * la)) * FXARM_R2D;
	FX_DOUBLE angb = 180 - anga - ang;

	if (j4type == -1)
	{
		anga += SPC->Ang1;
		angb += SPC->Ang2;
	}
	else
	{
		anga -= SPC->Ang1;
		angb -= SPC->Ang2;

	}

	FX_DOUBLE p1[3];
	FX_DOUBLE p2[3];


	p1[0] = 0; p1[1] = 0; p1[2] = 0;
	p2[0] = ablen; p2[1] = 0; p2[2] = 0;

	FX_DOUBLE v1x, v1y;
	FX_DOUBLE v2x, v2y;

	FX_SIN_COS_DEG(anga, &v1y, &v1x);
	FX_SIN_COS_DEG(180 - angb, &v2y, &v2x);


	/////  pt is axis_cross_eblow
	FX_DOUBLE pt[2];
	FX_SolveTrange2D(ablen, v1x, v1y, v2x, v2y, pt);

	FX_DOUBLE pta[2];
	FX_DOUBLE ptb[2];

	pta[0] = pt[0] * v1x * v1x;
	pta[1] = pt[0] * v1x * v1y;

	ptb[0] = ablen - (ablen - pt[0]) * (-v2x) * (-v2x);
	ptb[1] = (ablen - pt[0]) * (-v2x) * (v2y);

	va2b[0] /= ablen;
	va2b[1] /= ablen;
	va2b[2] /= ablen;

	FX_DOUBLE  Core[3];
	Core[0] = pa[0] + va2b[0] * pt[0];
	Core[1] = pa[1] + va2b[1] * pt[0];
	Core[2] = pa[2] + va2b[2] * pt[0];

	FX_DOUBLE cyclr = pt[1];

	FX_DOUBLE Len1 = FX_Sqrt(pt[0] * pt[0] + pt[1] * pt[1]);
	FX_DOUBLE Len2 = FX_Sqrt((ablen - pt[0]) * (ablen - pt[0]) + pt[1] * pt[1]);


	SPC->m_nsp.j4type = j4type;
	SPC->m_nsp.j4v = JV4;

	SPC->m_nsp.wristges[0][0] = m_flan[0][0];
	SPC->m_nsp.wristges[0][1] = m_flan[0][1];
	SPC->m_nsp.wristges[0][2] = m_flan[0][2];
	SPC->m_nsp.wristges[1][0] = m_flan[1][0];
	SPC->m_nsp.wristges[1][1] = m_flan[1][1];
	SPC->m_nsp.wristges[1][2] = m_flan[1][2];
	SPC->m_nsp.wristges[2][0] = m_flan[2][0];
	SPC->m_nsp.wristges[2][1] = m_flan[2][1];
	SPC->m_nsp.wristges[2][2] = m_flan[2][2];

	{
		FX_DOUBLE ref_j2_z_dir[3];
		FX_DOUBLE sinvj1;
		FX_DOUBLE cosvj1;
		FX_DOUBLE sinvj2;
		FX_DOUBLE cosvj2;

		FX_SIN_COS_DEG(solve_para->m_Input_IK_RefJoint[0], &sinvj1, &cosvj1);
		FX_SIN_COS_DEG(-solve_para->m_Input_IK_RefJoint[1], &sinvj2, &cosvj2);

		ref_j2_z_dir[0] = cosvj1 * sinvj2;
		ref_j2_z_dir[1] = sinvj1 * sinvj2;
		ref_j2_z_dir[2] = cosvj2;

		FX_DOUBLE ref_elbow_pos[3];
		ref_elbow_pos[0] = pa[0] + ref_j2_z_dir[0] * SPC->L1;
		ref_elbow_pos[1] = pa[1] + ref_j2_z_dir[1] * SPC->L1;
		ref_elbow_pos[2] = pa[2] + ref_j2_z_dir[2] * SPC->L1;

		FX_DOUBLE ref_vx[3];
		ref_vx[0] = ref_elbow_pos[0] - Core[0];
		ref_vx[1] = ref_elbow_pos[1] - Core[1];
		ref_vx[2] = ref_elbow_pos[2] - Core[2];

		if (solve_para->m_Input_IK_ZSPType == FX_PILOT_NSP_TYPES_NEAR_DIR)
		{
			ref_vx[0] = solve_para->m_Input_IK_ZSPPara[0];
			ref_vx[1] = solve_para->m_Input_IK_ZSPPara[1];
			ref_vx[2] = solve_para->m_Input_IK_ZSPPara[2];
		}

		FX_VectNorm(ref_vx);
		FX_DOUBLE tmp_vy[3];
		FX_VectCross(va2b, ref_vx, tmp_vy);
		FX_VectNorm(tmp_vy);
		FX_VectCross(tmp_vy, va2b, ref_vx);
		FX_VectNorm(ref_vx);

		FX_DOUBLE ref_near_elbow_pos[3];
		ref_near_elbow_pos[0] = Core[0] + ref_vx[0] * cyclr;
		ref_near_elbow_pos[1] = Core[1] + ref_vx[1] * cyclr;
		ref_near_elbow_pos[2] = Core[2] + ref_vx[2] * cyclr;


		FX_DOUBLE zero_angle_zdir[3];
		zero_angle_zdir[0] = ref_near_elbow_pos[0] - pa[0];
		zero_angle_zdir[1] = ref_near_elbow_pos[1] - pa[1];
		zero_angle_zdir[2] = ref_near_elbow_pos[2] - pa[2];

		FX_VectNorm(zero_angle_zdir);


		FX_DOUBLE zero_angle_xdir[3];

		zero_angle_xdir[0] = -ref_vx[0];
		zero_angle_xdir[1] = -ref_vx[1];
		zero_angle_xdir[2] = -ref_vx[2];

		FX_DOUBLE zero_angle_ydir[3];

		FX_VectCross(zero_angle_zdir, zero_angle_xdir, zero_angle_ydir);
		FX_VectNorm(zero_angle_ydir);

		FX_VectCross(zero_angle_ydir, zero_angle_zdir, zero_angle_xdir);
		FX_VectNorm(zero_angle_xdir);


		FX_DOUBLE zero_angle_zdir_b[3];
		zero_angle_zdir_b[0] = pb[0] - ref_near_elbow_pos[0];
		zero_angle_zdir_b[1] = pb[1] - ref_near_elbow_pos[1];
		zero_angle_zdir_b[2] = pb[2] - ref_near_elbow_pos[2];

		FX_VectNorm(zero_angle_zdir_b);
		FX_DOUBLE zero_angle_xdir_b[3];

		zero_angle_xdir_b[0] = -ref_vx[0];
		zero_angle_xdir_b[1] = -ref_vx[1];
		zero_angle_xdir_b[2] = -ref_vx[2];

		FX_DOUBLE zero_angle_ydir_b[3];

		FX_VectCross(zero_angle_zdir_b, zero_angle_xdir_b, zero_angle_ydir_b);
		FX_VectNorm(zero_angle_ydir_b);
		FX_VectCross(zero_angle_ydir_b, zero_angle_zdir_b, zero_angle_xdir_b);
		FX_VectNorm(zero_angle_xdir_b);


		SPC->m_nsp.rot_axis[0] = va2b[0];
		SPC->m_nsp.rot_axis[1] = va2b[1];
		SPC->m_nsp.rot_axis[2] = va2b[2];

		if (j4type == -1)
		{
			SPC->m_nsp.j123Base[0][0] = zero_angle_xdir[0];
			SPC->m_nsp.j123Base[1][0] = zero_angle_xdir[1];
			SPC->m_nsp.j123Base[2][0] = zero_angle_xdir[2];
			SPC->m_nsp.j123Base[0][1] = zero_angle_ydir[0];
			SPC->m_nsp.j123Base[1][1] = zero_angle_ydir[1];
			SPC->m_nsp.j123Base[2][1] = zero_angle_ydir[2];
			SPC->m_nsp.j123Base[0][2] = zero_angle_zdir[0];
			SPC->m_nsp.j123Base[1][2] = zero_angle_zdir[1];
			SPC->m_nsp.j123Base[2][2] = zero_angle_zdir[2];


			SPC->m_nsp.j567Base[0][0] = zero_angle_xdir_b[0];
			SPC->m_nsp.j567Base[1][0] = zero_angle_xdir_b[1];
			SPC->m_nsp.j567Base[2][0] = zero_angle_xdir_b[2];
			SPC->m_nsp.j567Base[0][1] = zero_angle_ydir_b[0];
			SPC->m_nsp.j567Base[1][1] = zero_angle_ydir_b[1];
			SPC->m_nsp.j567Base[2][1] = zero_angle_ydir_b[2];
			SPC->m_nsp.j567Base[0][2] = zero_angle_zdir_b[0];
			SPC->m_nsp.j567Base[1][2] = zero_angle_zdir_b[1];
			SPC->m_nsp.j567Base[2][2] = zero_angle_zdir_b[2];
		}
		else
		{
			SPC->m_nsp.j123Base[0][0] = -zero_angle_xdir[0];
			SPC->m_nsp.j123Base[1][0] = -zero_angle_xdir[1];
			SPC->m_nsp.j123Base[2][0] = -zero_angle_xdir[2];
			SPC->m_nsp.j123Base[0][1] = -zero_angle_ydir[0];
			SPC->m_nsp.j123Base[1][1] = -zero_angle_ydir[1];
			SPC->m_nsp.j123Base[2][1] = -zero_angle_ydir[2];
			SPC->m_nsp.j123Base[0][2] = zero_angle_zdir[0];
			SPC->m_nsp.j123Base[1][2] = zero_angle_zdir[1];
			SPC->m_nsp.j123Base[2][2] = zero_angle_zdir[2];

			SPC->m_nsp.j567Base[0][0] = -zero_angle_xdir_b[0];
			SPC->m_nsp.j567Base[1][0] = -zero_angle_xdir_b[1];
			SPC->m_nsp.j567Base[2][0] = -zero_angle_xdir_b[2];
			SPC->m_nsp.j567Base[0][1] = -zero_angle_ydir_b[0];
			SPC->m_nsp.j567Base[1][1] = -zero_angle_ydir_b[1];
			SPC->m_nsp.j567Base[2][1] = -zero_angle_ydir_b[2];
			SPC->m_nsp.j567Base[0][2] = zero_angle_zdir_b[0];
			SPC->m_nsp.j567Base[1][2] = zero_angle_zdir_b[1];
			SPC->m_nsp.j567Base[2][2] = zero_angle_zdir_b[2];
		}

	}

	solve_para->m_Output_RetJoint[3] = JV4;
	if (FX_SolveJ123ZNYZ(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[1])) == FX_FALSE)
	{
		return FX_FALSE;
	}
	if (SPC->m_IsCross == FX_TRUE)
	{
		if (FX_SolveJ567ZNYX(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}
	}
	else
	{
		if (FX_SolveJ567ZNYZ(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}

	}

	return FX_TRUE;
}

FX_BOOL  FX_InvKine_Pilot_teleop(FX_INT32L RobotSerial, FX_InvKineSolvePara * solve_para)
{
	double null_ang;
	FX_INT32L i;
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot * SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	NSPBase* NSP = &(SPC->m_nsp);
	solve_para->m_Output_IsOutRange = FX_FALSE;
	solve_para->m_Output_IsJntExd = FX_FALSE;
	solve_para->m_Input_ZSP_Angle = 0;
	for ( i = 0; i < 7; i++)
	{
		solve_para->m_Output_IsDeg[i] = FX_FALSE;
		solve_para->m_Output_JntExdTags[i] = FX_FALSE;
	}
	
	FX_DOUBLE m_flan[4][4];
	FX_DOUBLE m_wrist[4][4];
	FX_MMM44(solve_para->m_Input_IK_TargetTCP, pRobot->m_KineBase.m_InvTool, m_flan);
	FX_MMM44(m_flan, pRobot->m_KineBase.m_InvFlange, m_wrist);

	//// caculate point a (shoulder point) and point b (wrist point)
	FX_DOUBLE pa[3];
	FX_DOUBLE pb[3];

	pa[0] = pRobot->m_KineBase.m_JointPG[1][0][3];
	pa[1] = pRobot->m_KineBase.m_JointPG[1][1][3];
	pa[2] = pRobot->m_KineBase.m_JointPG[1][2][3];

	pb[0] = m_wrist[0][3];
	pb[1] = m_wrist[1][3];
	pb[2] = m_wrist[2][3];

	FX_DOUBLE  va2b[3];
	va2b[0] = pb[0] - pa[0];
	va2b[1] = pb[1] - pa[1];
	va2b[2] = pb[2] - pa[2];

	//// caculate j4 
	FX_DOUBLE ablen = FX_Sqrt(va2b[0] * va2b[0] + va2b[1] * va2b[1] + va2b[2] * va2b[2]);
	FX_DOUBLE max =SPC->L1 + SPC->L2 -10;
	FX_DOUBLE min = 260.0; //mm
	if (ablen> max)
	{	
		FX_DOUBLE scale = max/ ablen;
		va2b[0] *= scale;
		va2b[1] *= scale;
		va2b[2] *= scale;
		pb[0] = pa[0] + va2b[0];
		pb[1] = pa[1] + va2b[1];
		pb[2] = pa[2] + va2b[2];
		ablen = max;
	}
	else if (ablen < min)
	{
		FX_DOUBLE scale = min / ablen;
		va2b[0] *= scale;
		va2b[1] *= scale;
		va2b[2] *= scale;
		pb[0] = pa[0] + va2b[0];
		pb[1] = pa[1] + va2b[1];
		pb[2] = pa[2] + va2b[2];
		ablen = min;
	}
	

	FX_DOUBLE t = SPC->L1 * SPC->L1 + SPC->L2 * SPC->L2 - ablen * ablen;
	FX_DOUBLE ang = FX_ACOS(t / (2.0 * SPC->L1 * SPC->L2)) * FXARM_R2D;
	FX_DOUBLE Jv3[2];
	Jv3[0] = SPC->Angt - ang;
	Jv3[1] = SPC->Angt + ang - 360;

	FX_INT32 j4type = FX_GetJ4Type_Pilot(SPC, solve_para->m_Input_IK_RefJoint[3]);
	if (j4type == 0)
	{
		solve_para->m_Output_IsOutRange = FX_TRUE;
		return FX_FALSE;
	}

	FX_INT32 j4type1 = FX_GetJ4Type_Pilot(SPC, Jv3[0]);
	FX_INT32 j4type2 = FX_GetJ4Type_Pilot(SPC, Jv3[1]);

	FX_DOUBLE JV4;

	if (j4type == j4type1)
	{
		JV4 = Jv3[0];
	}
	else if (j4type == j4type2)
	{
		JV4 = Jv3[1];
	}
	else
	{
		solve_para->m_Output_IsOutRange = FX_TRUE;
		return FX_FALSE;
	}


	/// caculate shoulder axis_cross_elbow wrist trangle
	FX_DOUBLE la = SPC->L1;
	FX_DOUBLE lb = SPC->L2;
	FX_DOUBLE lc = ablen;
	FX_DOUBLE t1 = lc * lc + la * la - lb * lb;
	FX_DOUBLE anga = FX_ACOS(t1 / (2.0 * lc * la)) * FXARM_R2D;
	FX_DOUBLE angb = 180 - anga - ang;

	if (j4type == -1)
	{
		anga += SPC->Ang1;
		angb += SPC->Ang2;
	}
	else
	{
		anga -= SPC->Ang1;
		angb -= SPC->Ang2;

	}

	FX_DOUBLE p1[3];
	FX_DOUBLE p2[3];


	p1[0] = 0; p1[1] = 0; p1[2] = 0;
	p2[0] = ablen; p2[1] = 0; p2[2] = 0;

	FX_DOUBLE v1x, v1y;
	FX_DOUBLE v2x, v2y;

	FX_SIN_COS_DEG(anga, &v1y, &v1x);
	FX_SIN_COS_DEG(180 - angb, &v2y, &v2x);


	/////  pt is axis_cross_eblow
	FX_DOUBLE pt[2];
	FX_SolveTrange2D(ablen, v1x, v1y, v2x, v2y, pt);

	FX_DOUBLE pta[2];
	FX_DOUBLE ptb[2];

	pta[0] = pt[0] * v1x * v1x;
	pta[1] = pt[0] * v1x * v1y;

	ptb[0] = ablen - (ablen - pt[0]) * (-v2x) * (-v2x);
	ptb[1] = (ablen - pt[0]) * (-v2x) * (v2y);

	va2b[0] /= ablen;
	va2b[1] /= ablen;
	va2b[2] /= ablen;

	FX_DOUBLE  Core[3];
	Core[0] = pa[0] + va2b[0] * pt[0];
	Core[1] = pa[1] + va2b[1] * pt[0];
	Core[2] = pa[2] + va2b[2] * pt[0];

	FX_DOUBLE cyclr = pt[1];

	FX_DOUBLE Len1 = FX_Sqrt(pt[0] * pt[0] + pt[1] * pt[1]);
	FX_DOUBLE Len2 = FX_Sqrt((ablen - pt[0]) * (ablen - pt[0]) + pt[1] * pt[1]);


	SPC->m_nsp.j4type = j4type;
	SPC->m_nsp.j4v = JV4;

		FX_DOUBLE Vf_dir[3];

	Vf_dir[0] = pb[0] - m_flan[0][3];
	Vf_dir[1] = pb[1] - m_flan[1][3];
	Vf_dir[2] = pb[2] - m_flan[2][3];
	FX_DOUBLE angf = FX_ATan2(Vf_dir[0], Vf_dir[2]) * FXARM_R2D;
	// printf("angf = %f\n", angf);
	solve_para->angf = angf;


	SPC->m_nsp.wristges[0][0] = m_flan[0][0];
	SPC->m_nsp.wristges[0][1] = m_flan[0][1];
	SPC->m_nsp.wristges[0][2] = m_flan[0][2];
	SPC->m_nsp.wristges[1][0] = m_flan[1][0];
	SPC->m_nsp.wristges[1][1] = m_flan[1][1];
	SPC->m_nsp.wristges[1][2] = m_flan[1][2];
	SPC->m_nsp.wristges[2][0] = m_flan[2][0];
	SPC->m_nsp.wristges[2][1] = m_flan[2][1];
	SPC->m_nsp.wristges[2][2] = m_flan[2][2];


	{
		FX_DOUBLE ref_j2_z_dir[3];
		FX_DOUBLE sinvj1;
		FX_DOUBLE cosvj1;
		FX_DOUBLE sinvj2;
		FX_DOUBLE cosvj2;

		FX_SIN_COS_DEG(solve_para->m_Input_IK_RefJoint[0], &sinvj1, &cosvj1);
		FX_SIN_COS_DEG(-solve_para->m_Input_IK_RefJoint[1], &sinvj2, &cosvj2);

		ref_j2_z_dir[0] = cosvj1 * sinvj2;
		ref_j2_z_dir[1] = sinvj1 * sinvj2;
		ref_j2_z_dir[2] = cosvj2;

		FX_DOUBLE ref_elbow_pos[3];
		ref_elbow_pos[0] = pa[0] + ref_j2_z_dir[0] * SPC->L1;
		ref_elbow_pos[1] = pa[1] + ref_j2_z_dir[1] * SPC->L1;
		ref_elbow_pos[2] = pa[2] + ref_j2_z_dir[2] * SPC->L1;

		FX_DOUBLE ref_vx[3];
		ref_vx[0] = ref_elbow_pos[0] - Core[0];
		ref_vx[1] = ref_elbow_pos[1] - Core[1];
		ref_vx[2] = ref_elbow_pos[2] - Core[2];

		if (solve_para->m_Input_IK_ZSPType == FX_PILOT_NSP_TYPES_NEAR_DIR)
		{
			FX_DOUBLE ref_norm[3];
			// ref_vx[0] = solve_para->m_Input_IK_ZSPPara[0];
			// ref_vx[1] = solve_para->m_Input_IK_ZSPPara[1];
			// ref_vx[2] = solve_para->m_Input_IK_ZSPPara[2];
			ref_norm[0] = solve_para->m_Input_IK_ZSPPara[0];
			ref_norm[1] = solve_para->m_Input_IK_ZSPPara[1];
			ref_norm[2] = solve_para->m_Input_IK_ZSPPara[2];
			FX_VectCross(ref_norm,va2b,ref_vx);
		}

		FX_VectNorm(ref_vx);
		FX_DOUBLE tmp_vy[3];
		FX_VectCross(va2b, ref_vx, tmp_vy);
		FX_VectNorm(tmp_vy);
		FX_VectCross(tmp_vy, va2b, ref_vx);
		FX_VectNorm(ref_vx);

		FX_DOUBLE ref_near_elbow_pos[3];
		ref_near_elbow_pos[0] = Core[0] + ref_vx[0] * cyclr;
		ref_near_elbow_pos[1] = Core[1] + ref_vx[1] * cyclr;
		ref_near_elbow_pos[2] = Core[2] + ref_vx[2] * cyclr;


		FX_DOUBLE zero_angle_zdir[3];
		zero_angle_zdir[0] = ref_near_elbow_pos[0] - pa[0];
		zero_angle_zdir[1] = ref_near_elbow_pos[1] - pa[1];
		zero_angle_zdir[2] = ref_near_elbow_pos[2] - pa[2];

		FX_VectNorm(zero_angle_zdir);


		FX_DOUBLE zero_angle_xdir[3];

		zero_angle_xdir[0] = -ref_vx[0];
		zero_angle_xdir[1] = -ref_vx[1];
		zero_angle_xdir[2] = -ref_vx[2];

		FX_DOUBLE zero_angle_ydir[3];

		FX_VectCross(zero_angle_zdir, zero_angle_xdir, zero_angle_ydir);
		FX_VectNorm(zero_angle_ydir);

		FX_VectCross(zero_angle_ydir, zero_angle_zdir, zero_angle_xdir);
		FX_VectNorm(zero_angle_xdir);


		FX_DOUBLE zero_angle_zdir_b[3];
		zero_angle_zdir_b[0] = pb[0] - ref_near_elbow_pos[0];
		zero_angle_zdir_b[1] = pb[1] - ref_near_elbow_pos[1];
		zero_angle_zdir_b[2] = pb[2] - ref_near_elbow_pos[2];

		FX_VectNorm(zero_angle_zdir_b);
		FX_DOUBLE zero_angle_xdir_b[3];

		zero_angle_xdir_b[0] = -ref_vx[0];
		zero_angle_xdir_b[1] = -ref_vx[1];
		zero_angle_xdir_b[2] = -ref_vx[2];

		FX_DOUBLE zero_angle_ydir_b[3];

		FX_VectCross(zero_angle_zdir_b, zero_angle_xdir_b, zero_angle_ydir_b);
		FX_VectNorm(zero_angle_ydir_b);
		FX_VectCross(zero_angle_ydir_b, zero_angle_zdir_b, zero_angle_xdir_b);
		FX_VectNorm(zero_angle_xdir_b);


		SPC->m_nsp.rot_axis[0] = va2b[0];
		SPC->m_nsp.rot_axis[1] = va2b[1];
		SPC->m_nsp.rot_axis[2] = va2b[2];

		if (j4type == -1)
		{
			SPC->m_nsp.j123Base[0][0] = zero_angle_xdir[0];
			SPC->m_nsp.j123Base[1][0] = zero_angle_xdir[1];
			SPC->m_nsp.j123Base[2][0] = zero_angle_xdir[2];
			SPC->m_nsp.j123Base[0][1] = zero_angle_ydir[0];
			SPC->m_nsp.j123Base[1][1] = zero_angle_ydir[1];
			SPC->m_nsp.j123Base[2][1] = zero_angle_ydir[2];
			SPC->m_nsp.j123Base[0][2] = zero_angle_zdir[0];
			SPC->m_nsp.j123Base[1][2] = zero_angle_zdir[1];
			SPC->m_nsp.j123Base[2][2] = zero_angle_zdir[2];


			SPC->m_nsp.j567Base[0][0] = zero_angle_xdir_b[0];
			SPC->m_nsp.j567Base[1][0] = zero_angle_xdir_b[1];
			SPC->m_nsp.j567Base[2][0] = zero_angle_xdir_b[2];
			SPC->m_nsp.j567Base[0][1] = zero_angle_ydir_b[0];
			SPC->m_nsp.j567Base[1][1] = zero_angle_ydir_b[1];
			SPC->m_nsp.j567Base[2][1] = zero_angle_ydir_b[2];
			SPC->m_nsp.j567Base[0][2] = zero_angle_zdir_b[0];
			SPC->m_nsp.j567Base[1][2] = zero_angle_zdir_b[1];
			SPC->m_nsp.j567Base[2][2] = zero_angle_zdir_b[2];
		}
		else
		{
			SPC->m_nsp.j123Base[0][0] = -zero_angle_xdir[0];
			SPC->m_nsp.j123Base[1][0] = -zero_angle_xdir[1];
			SPC->m_nsp.j123Base[2][0] = -zero_angle_xdir[2];
			SPC->m_nsp.j123Base[0][1] = -zero_angle_ydir[0];
			SPC->m_nsp.j123Base[1][1] = -zero_angle_ydir[1];
			SPC->m_nsp.j123Base[2][1] = -zero_angle_ydir[2];
			SPC->m_nsp.j123Base[0][2] = zero_angle_zdir[0];
			SPC->m_nsp.j123Base[1][2] = zero_angle_zdir[1];
			SPC->m_nsp.j123Base[2][2] = zero_angle_zdir[2];

			SPC->m_nsp.j567Base[0][0] = -zero_angle_xdir_b[0];
			SPC->m_nsp.j567Base[1][0] = -zero_angle_xdir_b[1];
			SPC->m_nsp.j567Base[2][0] = -zero_angle_xdir_b[2];
			SPC->m_nsp.j567Base[0][1] = -zero_angle_ydir_b[0];
			SPC->m_nsp.j567Base[1][1] = -zero_angle_ydir_b[1];
			SPC->m_nsp.j567Base[2][1] = -zero_angle_ydir_b[2];
			SPC->m_nsp.j567Base[0][2] = zero_angle_zdir_b[0];
			SPC->m_nsp.j567Base[1][2] = zero_angle_zdir_b[1];
			SPC->m_nsp.j567Base[2][2] = zero_angle_zdir_b[2];
		}

		// null space angle 

		// Calculate normal direction of the plane formed by va2b and Vf_dir
	FX_DOUBLE plane_normal[3];
	FX_DOUBLE ref_vz_norm[3];
	FX_DOUBLE ref_vz[3];


	FX_VectCross(ref_vx,va2b,ref_vz);
	ref_vz_norm[0] = -ref_vz[0];
	ref_vz_norm[1] = -ref_vz[1];
	ref_vz_norm[2] = -ref_vz[2];
	FX_VectNorm(ref_vz_norm);
	FX_VectCross(va2b, Vf_dir, plane_normal);
	FX_VectNorm(plane_normal);
	FX_DOUBLE angnull = FX_ACOS(ref_vz_norm[0] * plane_normal[0] + ref_vz_norm[1] * plane_normal[1] + ref_vz_norm[2] * plane_normal[2]);
	solve_para->m_Input_ZSP_Angle = angnull*180.0/FXARM_PI;
	// printf("null ang = %f\n", angnull);

	// Calculate the null space vector from Core to elbow in the plane of va2b and Vf_dir
	// FX_DOUBLE null_space_elbow_dir[3];
	// FX_VectCross(plane_normal, va2b, null_space_elbow_dir);
	FX_VectNorm(plane_normal);
	solve_para->m_null_elbow[0] = plane_normal[0];
	solve_para->m_null_elbow[1] = plane_normal[1];
	solve_para->m_null_elbow[2] = plane_normal[2];
	// solve_para->m_Input_ZSP_Angle
	// double null_angle = 

		// // solve_para->m_Input_ZSP_Angle =  -FXARM_PI + null_ang;
		
		// printf("null ang = %f\n", signed_angle);
	}

	solve_para->m_Output_RetJoint[3] = JV4;
	if (FX_SolveJ123ZNYZ(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[1])) == FX_FALSE)
	{
		return FX_FALSE;
	}
	if (SPC->m_IsCross == FX_TRUE)
	{
		if (FX_SolveJ567ZNYX(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}
	}
	else
	{
		if (FX_SolveJ567ZNYZ(NSP, 0, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}

	}

	return FX_TRUE;
}


FX_BOOL  FX_InvKine_Pilot_SRS(FX_INT32L RobotSerial, FX_InvKineSolvePara* solve_para)
{
	if (FX_InvKine_Pilot(RobotSerial, solve_para) == FX_FALSE)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	NSPBase* NSP = &(SPC->m_nsp);

	FX_INT32L i;
	solve_para->m_Output_IsJntExd = FX_FALSE;
	for ( i = 0; i < 7; i++)
	{
		solve_para->m_Output_RunLmtP[i] = pRobot->m_Lmt.m_JLmtPos_P[i];
		solve_para->m_Output_RunLmtN[i] = pRobot->m_Lmt.m_JLmtPos_N[i];
		if (solve_para->m_Output_RetJoint[i] < solve_para->m_Output_RunLmtN[i] || solve_para->m_Output_RetJoint[i] > solve_para->m_Output_RunLmtP[i])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[i] = FX_TRUE;
		}
		else
		{
			solve_para->m_Output_JntExdTags[i] = FX_FALSE;
		}
	}
	return FX_TRUE;
}
FX_BOOL  FX_InvKine_Pilot_CCS(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para)
{
	if (FX_InvKine_Pilot_teleop(RobotSerial, solve_para) == FX_FALSE)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	NSPBase* NSP = &(SPC->m_nsp);

	FX_INT32L i;
	solve_para->m_Output_IsJntExd = FX_FALSE;
	for (i = 0; i < 7; i++)
	{
		solve_para->m_Output_RunLmtP[i] = pRobot->m_Lmt.m_JLmtPos_P[i];
		solve_para->m_Output_RunLmtN[i] = pRobot->m_Lmt.m_JLmtPos_N[i];
		if (solve_para->m_Output_RetJoint[i] < solve_para->m_Output_RunLmtN[i] || solve_para->m_Output_RetJoint[i] > solve_para->m_Output_RunLmtP[i])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[i] = FX_TRUE;
		}
		else
		{
			solve_para->m_Output_JntExdTags[i] = FX_FALSE;
		}
	}

	
	if (solve_para->m_Output_RetJoint[5] > 1)
	{
		FX_DOUBLE J6 = solve_para->m_Output_RetJoint[5];
		if (J6 > solve_para->m_Output_RunLmtP[5])
		{
			J6 = solve_para->m_Output_RunLmtP[5];
		}
		FX_DOUBLE P = SPC->lmtj67_pp[0] * J6 * J6 + SPC->lmtj67_pp[1] *  J6 + SPC->lmtj67_pp[2];
		if (solve_para->m_Output_RunLmtP[6] > P)
		{
			solve_para->m_Output_RunLmtP[6] = P;
		}
		if (solve_para->m_Output_RetJoint[6] > solve_para->m_Output_RunLmtP[6])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[6] = FX_TRUE;
		}

		FX_DOUBLE N = SPC->lmtj67_pn[0] * J6 * J6 + SPC->lmtj67_pn[1] * J6 + SPC->lmtj67_pn[2];
		if (solve_para->m_Output_RunLmtN[6] < N)
		{
			solve_para->m_Output_RunLmtN[6] = N;
		}
		if (solve_para->m_Output_RetJoint[6] < solve_para->m_Output_RunLmtN[6])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[6] = FX_TRUE;
		}


		return FX_TRUE;
	}


	if (solve_para->m_Output_RetJoint[5] < -1)
	{
		FX_DOUBLE J6 = solve_para->m_Output_RetJoint[5];
		if (J6 > solve_para->m_Output_RunLmtP[5])
		{
			J6 = solve_para->m_Output_RunLmtP[5];
		}
		FX_DOUBLE P = SPC->lmtj67_np[0] * J6 * J6 + SPC->lmtj67_np[1] * J6 + SPC->lmtj67_np[2];
		if (solve_para->m_Output_RunLmtP[6] > P)
		{
			solve_para->m_Output_RunLmtP[6] = P;
		}
		if (solve_para->m_Output_RetJoint[6] > solve_para->m_Output_RunLmtP[6])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[6] = FX_TRUE;
		}

		FX_DOUBLE N = SPC->lmtj67_nn[0] * J6 * J6 + SPC->lmtj67_nn[1] * J6 + SPC->lmtj67_nn[2];
		if (solve_para->m_Output_RunLmtN[6] < N)
		{
			solve_para->m_Output_RunLmtN[6] = N;
		}
		if (solve_para->m_Output_RetJoint[6] < solve_para->m_Output_RunLmtN[6])
		{
			solve_para->m_Output_IsJntExd = FX_TRUE;
			solve_para->m_Output_JntExdTags[6] = FX_TRUE;
		}


		return FX_TRUE;
	}


	return FX_TRUE;
}

FX_BOOL  FX_Robot_Kine_IK(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		return FX_InvKine_DL(RobotSerial, solve_para);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS)
	{
		return FX_InvKine_Pilot_SRS(RobotSerial, solve_para);
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		return FX_InvKine_Pilot_CCS(RobotSerial, solve_para);
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_BOOL  FX_InvKineNSP_Pilot(FX_INT32L RobotSerial, FX_InvKineSolvePara* solve_para)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineSPC_Pilot* SPC = (FX_KineSPC_Pilot*)(pRobot->m_KineSPC);
	NSPBase* NSP = &(SPC->m_nsp);

	solve_para->m_Output_IsDeg[1] = FX_FALSE;
	solve_para->m_Output_IsDeg[5] = FX_FALSE;
	

	solve_para->m_Output_RetJoint[3] = NSP->j4v;
	if (FX_SolveJ123ZNYZ(NSP, solve_para->m_Input_ZSP_Angle, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[1])) == FX_FALSE)
	{
		return FX_FALSE;
	}
	if (NSP->m_IsCorss == FX_TRUE)
	{
		if (FX_SolveJ567ZNYX(NSP, solve_para->m_Input_ZSP_Angle, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}

		FX_INT32L i;
		solve_para->m_Output_IsJntExd = FX_FALSE;
		for (i = 0; i < 7; i++)
		{
			solve_para->m_Output_RunLmtP[i] = pRobot->m_Lmt.m_JLmtPos_P[i];
			solve_para->m_Output_RunLmtN[i] = pRobot->m_Lmt.m_JLmtPos_N[i];
			if (solve_para->m_Output_RetJoint[i] < solve_para->m_Output_RunLmtN[i] || solve_para->m_Output_RetJoint[i] > solve_para->m_Output_RunLmtP[i])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[i] = FX_TRUE;
			}
			else
			{
				solve_para->m_Output_JntExdTags[i] = FX_FALSE;
			}
		}


		if (solve_para->m_Output_RetJoint[5] > 1)
		{
			FX_DOUBLE J6 = solve_para->m_Output_RetJoint[5];
			if (J6 > solve_para->m_Output_RunLmtP[5])
			{
				J6 = solve_para->m_Output_RunLmtP[5];
			}
			FX_DOUBLE P = SPC->lmtj67_pp[0] * J6 * J6 + SPC->lmtj67_pp[1] * J6 + SPC->lmtj67_pp[2];
			if (solve_para->m_Output_RunLmtP[6] > P)
			{
				solve_para->m_Output_RunLmtP[6] = P;
			}
			if (solve_para->m_Output_RetJoint[6] > solve_para->m_Output_RunLmtP[6])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[6] = FX_TRUE;
			}

			FX_DOUBLE N = SPC->lmtj67_pn[0] * J6 * J6 + SPC->lmtj67_pn[1] * J6 + SPC->lmtj67_pn[2];
			if (solve_para->m_Output_RunLmtN[6] < N)
			{
				solve_para->m_Output_RunLmtN[6] = N;
			}
			if (solve_para->m_Output_RetJoint[6] < solve_para->m_Output_RunLmtN[6])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[6] = FX_TRUE;
			}


			return FX_TRUE;
		}


		if (solve_para->m_Output_RetJoint[5] < -1)
		{
			FX_DOUBLE J6 = solve_para->m_Output_RetJoint[5];
			if (J6 > solve_para->m_Output_RunLmtP[5])
			{
				J6 = solve_para->m_Output_RunLmtP[5];
			}
			FX_DOUBLE P = SPC->lmtj67_np[0] * J6 * J6 + SPC->lmtj67_np[1] * J6 + SPC->lmtj67_np[2];
			if (solve_para->m_Output_RunLmtP[6] > P)
			{
				solve_para->m_Output_RunLmtP[6] = P;
			}
			if (solve_para->m_Output_RetJoint[6] > solve_para->m_Output_RunLmtP[6])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[6] = FX_TRUE;
			}

			FX_DOUBLE N = SPC->lmtj67_nn[0] * J6 * J6 + SPC->lmtj67_nn[1] * J6 + SPC->lmtj67_nn[2];
			if (solve_para->m_Output_RunLmtN[6] < N)
			{
				solve_para->m_Output_RunLmtN[6] = N;
			}
			if (solve_para->m_Output_RetJoint[6] < solve_para->m_Output_RunLmtN[6])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[6] = FX_TRUE;
			}


			return FX_TRUE;
		}
	}
	else
	{
		if (FX_SolveJ567ZNYZ(NSP, solve_para->m_Input_ZSP_Angle, solve_para->m_Input_IK_RefJoint, solve_para->m_Output_RetJoint, &(solve_para->m_Output_IsDeg[5])) == FX_FALSE)
		{
			return FX_FALSE;
		}

		FX_INT32L i;
		solve_para->m_Output_IsJntExd = FX_FALSE;
		for (i = 0; i < 7; i++)
		{
			solve_para->m_Output_RunLmtP[i] = pRobot->m_Lmt.m_JLmtPos_P[i];
			solve_para->m_Output_RunLmtN[i] = pRobot->m_Lmt.m_JLmtPos_N[i];
			if (solve_para->m_Output_RetJoint[i] < solve_para->m_Output_RunLmtN[i] || solve_para->m_Output_RetJoint[i] > solve_para->m_Output_RunLmtP[i])
			{
				solve_para->m_Output_IsJntExd = FX_TRUE;
				solve_para->m_Output_JntExdTags[i] = FX_TRUE;
			}
			else
			{
				solve_para->m_Output_JntExdTags[i] = FX_FALSE;
			}
		}

	}

	return FX_TRUE;
}

FX_BOOL  FX_Robot_Kine_IK_NSP(FX_INT32L RobotSerial, FX_InvKineSolvePara *solve_para)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	if (pRobot->m_RobotType == FX_ROBOT_TYPE_DL)
	{
		return FX_FALSE;
	}
	else if (pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_SRS || pRobot->m_RobotType == FX_ROBOT_TYPE_PILOT_CCS)
	{
		return FX_InvKineNSP_Pilot(RobotSerial, solve_para);
	}
	else
	{
		return FX_FALSE;
	}
	return FX_FALSE;
}
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_BOOL  FX_Robot_Init_Dyna(FX_INT32L RobotSerial, Vect3 GRV, FX_DOUBLE Mass[7], Vect3 MCP[7], Vect6 I[7])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	Matrix4 Tran;
	Matrix4 PG;
	Matrix4 PG_tmp;
	FX_IdentM44(PG);
	Vect7 t = {0};
	Matrix4 pgt;

	FX_DOUBLE BI[3][3];
	FX_DOUBLE BMCP[3];

	for ( i = 0; i < 7; i++)
	{
		t[i] = 0;
	}
	FX_Robot_Kine_FK(RobotSerial, t, pgt);
	for ( i = 0; i < pRobot->m_RobotDOF; i++)
	{
		Tmat(pRobot->m_RobotDH[i], Tran);
		FX_PGMult(PG, Tran, PG_tmp);
		FX_M44Copy(PG_tmp, PG);

		pRobot->m_DynaBase.m_JntMass[i] = Mass[i];
		BMCP[0] = MCP[i][0];
		BMCP[1] = MCP[i][1];
		BMCP[2] = MCP[i][2];
		BI[0][0] = I[i][0];
		BI[0][1] = I[i][1];
		BI[1][0] = I[i][1];
		BI[0][2] = I[i][2];
		BI[2][0] = I[i][2];
		BI[1][1] = I[i][3];
		BI[1][2] = I[i][4];
		BI[2][1] = I[i][4];
		BI[2][2] = I[i][5];
		FX_Robot_Dyna_Map_DynPara_B2A(kine->m_JointPG[i], PG, BI, BMCP, 
			pRobot->m_DynaBase.m_JntInertia[i], pRobot->m_DynaBase.m_JntMCP[i]);
	}
	pRobot->m_DynaBase.m_NToolTag = FX_FALSE;
	pRobot->m_DynaBase.m_BaseFloatationTag = FX_FALSE;
	FX_Robot_Tool_RmvDyn(RobotSerial);
	pRobot->m_DynaBase.m_CalGravity[0] = GRV[0];
	pRobot->m_DynaBase.m_CalGravity[1] = GRV[1];
	pRobot->m_DynaBase.m_CalGravity[2] = GRV[2];
	pRobot->m_DynaBase.m_SettingGravity[0] = GRV[0];
	pRobot->m_DynaBase.m_SettingGravity[1] = GRV[1];
	pRobot->m_DynaBase.m_SettingGravity[2] = GRV[2];
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Init_Dyna_Set_VirTool(FX_INT32L RobotSerial, FX_DOUBLE Mass, Vect3 MCP, Vect6 I)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	
	pRobot->m_DynaBase.m_NToolMass = Mass;
	pRobot->m_DynaBase.m_NToolMCP[0] = MCP[0];
	pRobot->m_DynaBase.m_NToolMCP[1] = MCP[1];
	pRobot->m_DynaBase.m_NToolMCP[2] = MCP[2];
	pRobot->m_DynaBase.m_NToolInertia[0][0] = I[0];
	pRobot->m_DynaBase.m_NToolInertia[0][1] = I[1];
	pRobot->m_DynaBase.m_NToolInertia[1][0] = I[1];
	pRobot->m_DynaBase.m_NToolInertia[0][2] = I[2];
	pRobot->m_DynaBase.m_NToolInertia[2][0] = I[2];
	pRobot->m_DynaBase.m_NToolInertia[1][1] = I[3];
	pRobot->m_DynaBase.m_NToolInertia[1][2] = I[4];
	pRobot->m_DynaBase.m_NToolInertia[2][1] = I[4];
	pRobot->m_DynaBase.m_NToolInertia[2][2] = I[5];

	pRobot->m_DynaBase.m_NToolTag = FX_TRUE;
	return FX_TRUE;
}


FX_BOOL  FX_Robot_Tool_SetDyn(FX_INT32L RobotSerial, FX_DOUBLE Mass, Vect3 MCP, Vect6 I)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	pRobot->m_DynaBase.m_ToolMass = Mass;
	pRobot->m_DynaBase.m_ToolMCP[0] = MCP[0];
	pRobot->m_DynaBase.m_ToolMCP[1] = MCP[1];
	pRobot->m_DynaBase.m_ToolMCP[2] = MCP[2];
	pRobot->m_DynaBase.m_ToolInertia[0][0] = I[0];
	pRobot->m_DynaBase.m_ToolInertia[0][1] = I[1];
	pRobot->m_DynaBase.m_ToolInertia[1][0] = I[1];
	pRobot->m_DynaBase.m_ToolInertia[0][2] = I[2];
	pRobot->m_DynaBase.m_ToolInertia[2][0] = I[2];
	pRobot->m_DynaBase.m_ToolInertia[1][1] = I[3];
	pRobot->m_DynaBase.m_ToolInertia[1][2] = I[4];
	pRobot->m_DynaBase.m_ToolInertia[2][1] = I[4];
	pRobot->m_DynaBase.m_ToolInertia[2][2] = I[5];
	return FX_TRUE;
}
FX_BOOL  FX_Robot_Tool_RmvDyn(FX_INT32L RobotSerial)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	pRobot->m_DynaBase.m_ToolMass = 0;
	pRobot->m_DynaBase.m_ToolMCP[0] = 0;
	pRobot->m_DynaBase.m_ToolMCP[1] = 0;
	pRobot->m_DynaBase.m_ToolMCP[2] = 0;
	pRobot->m_DynaBase.m_ToolInertia[0][0] = 0;
	pRobot->m_DynaBase.m_ToolInertia[0][1] = 0;
	pRobot->m_DynaBase.m_ToolInertia[1][0] = 0;
	pRobot->m_DynaBase.m_ToolInertia[0][2] = 0;
	pRobot->m_DynaBase.m_ToolInertia[2][0] = 0;
	pRobot->m_DynaBase.m_ToolInertia[1][1] = 0;
	pRobot->m_DynaBase.m_ToolInertia[1][2] = 0;
	pRobot->m_DynaBase.m_ToolInertia[2][1] = 0;
	pRobot->m_DynaBase.m_ToolInertia[2][2] = 0;
	return FX_TRUE;
}

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

FX_VOID InertiaTran(Matrix3 input_i_b, Matrix3 input_b2a, Matrix3 output_i_a)
{
	{
		Matrix3 ma2b;
		FX_M33Trans(input_b2a, ma2b);
		Matrix3 mtmp;
		FX_MMM33(input_b2a, input_i_b, mtmp);
		FX_MMM33(mtmp, ma2b, output_i_a);
	}

	{
		Matrix3 ma2b;
		FX_M33Trans(input_b2a, ma2b);
		Matrix3 mtmp;
		FX_MMM33(input_b2a, input_i_b, mtmp);
		FX_MMM33(mtmp, ma2b, output_i_a);
	}
	
}




FX_BOOL FX_Robot_Dyna_CalBase(FX_INT32L RobotSerial, Vect7 angle)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fpos = dof - 1;
	if (Fpos < 0)
	{
		Fpos = 0;
	}
	
	Matrix4   pg;
	FX_Robot_Kine_FK(RobotSerial, angle, pg);
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;


	Matrix3   ges;
	for  (i = 0; i < pRobot->m_RobotDOF; i++)
	{
		FX_PGGetGes(kine->m_JointPG[i], ges);
		InertiaTran(dyn->m_JntInertia[i], ges, dyn->m_JntInertia_inBase[i]);
		FX_PGPointMap(kine->m_JointPG[i], dyn->m_JntMCP[i], dyn->m_JntMCP_inBase[i]);
		FX_PGGetAxisZ(kine->m_JointPG[i], dyn->m_JntRotAxisDir_inBase[i]);
	}

	FX_PGGetGes(kine->m_FlangeTip, ges);
	InertiaTran(dyn->m_ToolInertia, ges, dyn->m_ToolInertia_inBase);
	FX_PGPointMap(kine->m_FlangeTip, dyn->m_ToolMCP, dyn->m_ToolMCP_inBase);
	if (dyn->m_NToolTag == FX_TRUE)
	{
		InertiaTran(dyn->m_NToolInertia, ges, dyn->m_NToolInertia_inBase);
		FX_PGPointMap(kine->m_FlangeTip, dyn->m_NToolMCP, dyn->m_NToolMCP_inBase);
	}

	return FX_TRUE;
}




FX_BOOL  FX_Robot_CalSigOmgD_Fix(FX_INT32L RobotSerial, FX_INT32L AxisSerial, Vect7 ret_Tau)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF - 1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}
	if (AxisSerial < 0 || AxisSerial >= dof)
	{
		return FX_FALSE;
	}


	Vect3 omgd;
	omgd[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial][0];
	omgd[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial][1];
	omgd[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial][2];

	Vect3 F[8];
	Vect3 N[8];

	for (i = 0; i < dof; i++)
	{
		if (i < AxisSerial)
		{
			F[i][0] = 0;
			F[i][1] = 0;
			F[i][2] = 0;

			N[i][0] = 0;
			N[i][1] = 0;
			N[i][2] = 0;
		}
		else
		{
			FX_MMV3(dyn->m_JntInertia_inBase[i], omgd, N[i]);

			Vect3 _to_mcp;
			_to_mcp[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[AxisSerial][0][3]);
			_to_mcp[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[AxisSerial][1][3]);
			_to_mcp[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[AxisSerial][2][3]);
			Vect3 acc;
			FX_VectCross(omgd, _to_mcp, acc);
			F[i][0] = (acc[0]) * dyn->m_JntMass[i];
			F[i][1] = (acc[1]) * dyn->m_JntMass[i];
			F[i][2] = (acc[2]) * dyn->m_JntMass[i];
		}
	}

	Vect3 F_Tool;
	Vect3 N_Tool;
	{
		FX_MMV3(dyn->m_ToolInertia_inBase, omgd, N_Tool);

		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[AxisSerial][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[AxisSerial][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[AxisSerial][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		F_Tool[0] = (acc[0]) * dyn->m_ToolMass;
		F_Tool[1] = (acc[1]) * dyn->m_ToolMass;
		F_Tool[2] = (acc[2]) * dyn->m_ToolMass;
	}


	Vect3 F_NTool;
	Vect3 N_NTool;
	if(dyn->m_NToolTag == FX_TRUE)
	{
		Vect3 tmp;
		FX_MMV3(dyn->m_NToolInertia_inBase, omgd, tmp);
		N_NTool[0] = -tmp[0];
		N_NTool[1] = -tmp[1];
		N_NTool[2] = -tmp[2];
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[AxisSerial][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[AxisSerial][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[AxisSerial][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		F_NTool[0] = - (acc[0]) * dyn->m_NToolMass;
		F_NTool[1] = - (acc[1]) * dyn->m_NToolMass;
		F_NTool[2] = - (acc[2]) * dyn->m_NToolMass;
	}

	Vect3 flange_f;
	{
		flange_f[0] = F_Tool[0];
		flange_f[1] = F_Tool[1];
		flange_f[2] = F_Tool[2];
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, F_NTool);
		}
	}
	Vect3 flange_n;
	{
		flange_n[0] = N_Tool[0];
		flange_n[1] = N_Tool[1];
		flange_n[2] = N_Tool[2];

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, F_Tool, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, N_NTool);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, F_NTool, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for (i = Fdof; i >= 0; i--)
	{
		if (i == Fdof)
		{
			FX_VectAdd(F[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);
			to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, F[i], n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);

		}
		else
		{
			FX_VectAdd(F[i], dyn->m_Link_F_inBase[i + 1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], dyn->m_Link_N_inBase[i + 1], dyn->m_Link_N_inBase[i]);

			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_JointPG[i + 1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_JointPG[i + 1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_JointPG[i + 1][2][3] - kine->m_JointPG[i][2][3]);
			Vect3 n_nxt;
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			if (i >= AxisSerial)
			{
				Vect3 to_mcp_v;
				to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
				to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
				to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]); 
				Vect3 n_mcp;
				FX_VectCross(to_mcp_v, F[i], n_mcp);
				FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
			}
		}
		ret_Tau[i] = kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0]
			+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1]
			+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}
	return FX_TRUE;
}



FX_BOOL  FX_Robot_Dyna_MOI_Mat_Fix(FX_INT32L RobotSerial, Matrix7 ret_MOImat)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L i, j, jj, ii;
	FX_INT32L aa = 0;
	FX_INT32L bb = 1;

	FX_DOUBLE tau[7] = { 0 };
	for (jj = 0; jj < dof; jj++) {
		
		FX_Robot_CalSigOmgD_Fix(RobotSerial, jj, tau);
		for (ii = 0; ii < 7; ii++) {
			ret_MOImat[ii][jj] = tau[ii];
		}
	
	}

	for (i = aa; i < 7; i++) {
		for (j = bb; j < 7; j++) {
			ret_MOImat[i][j] = ret_MOImat[j][i];
		}
		aa++;
		bb++;
	}

	return FX_TRUE;
	
}



FX_BOOL  FX_Robot_CalSigOmg_Fix(FX_INT32L RobotSerial, FX_INT32L AxisSerial, Vect7 ret_Tau)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF - 1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}
	if (AxisSerial < 0 || AxisSerial >= dof)
	{
		return FX_FALSE;
	}


	Vect3 omg;
	omg[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial][0];
	omg[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial][1];
	omg[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial][2];

	Vect3 F[8];
	Vect3 N[8];

	for (i = 0; i < dof; i++)
	{
		if (i < AxisSerial)
		{
			F[i][0] = 0;
			F[i][1] = 0;
			F[i][2] = 0;

			N[i][0] = 0;
			N[i][1] = 0;
			N[i][2] = 0;
		}
		else
		{
			Vect3 rtmp;
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg, rtmp);
			FX_VectCross(omg, rtmp, N[i]);
			Vect3 _to_mcp;
			_to_mcp[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[AxisSerial][0][3]);
			_to_mcp[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[AxisSerial][1][3]);
			_to_mcp[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[AxisSerial][2][3]);
			Vect3 acc_t;
			FX_VectCross(omg, _to_mcp, acc_t);
			Vect3 acc;
			FX_VectCross(omg, acc_t, acc);
			F[i][0] = (acc[0]) * dyn->m_JntMass[i];
			F[i][1] = (acc[1]) * dyn->m_JntMass[i];
			F[i][2] = (acc[2]) * dyn->m_JntMass[i];
		}
	}

	Vect3 F_Tool;
	Vect3 N_Tool;
	{
		Vect3 rtmp;
		FX_MMV3(dyn->m_ToolInertia_inBase, omg, rtmp);
		FX_VectCross(omg, rtmp, N_Tool);

		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[AxisSerial][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[AxisSerial][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[AxisSerial][2][3]);
		Vect3 acc_t;
		FX_VectCross(omg, _to_mcp, acc_t);
		Vect3 acc;
		FX_VectCross(omg, acc_t, acc);
		F_Tool[0] = (acc[0]) * dyn->m_ToolMass;
		F_Tool[1] = (acc[1]) * dyn->m_ToolMass;
		F_Tool[2] = (acc[2]) * dyn->m_ToolMass;
	}


	Vect3 F_NTool;
	Vect3 N_NTool;

	if (dyn->m_NToolTag == FX_TRUE)
	{
		Vect3 tmp;
		Vect3 rtmp;
		FX_MMV3(dyn->m_NToolInertia_inBase, omg, rtmp);
		FX_VectCross(omg, rtmp, tmp);
		N_NTool[0] = -tmp[0];
		N_NTool[1] = -tmp[1];
		N_NTool[2] = -tmp[2];
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[AxisSerial][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[AxisSerial][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[AxisSerial][2][3]);
		Vect3 acc_t;
		FX_VectCross(omg, _to_mcp, acc_t);
		Vect3 acc;
		FX_VectCross(omg, acc_t, acc);
		F_NTool[0] = -(acc[0]) * dyn->m_NToolMass;
		F_NTool[1] = -(acc[1]) * dyn->m_NToolMass;
		F_NTool[2] = -(acc[2]) * dyn->m_NToolMass;
	}

	Vect3 flange_f;
	{
		flange_f[0] = F_Tool[0];
		flange_f[1] = F_Tool[1];
		flange_f[2] = F_Tool[2];
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, F_NTool);
		}
	}
	Vect3 flange_n;
	{
		flange_n[0] = N_Tool[0];
		flange_n[1] = N_Tool[1];
		flange_n[2] = N_Tool[2];

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, F_Tool, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, N_NTool);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, F_NTool, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for (i = Fdof; i >= 0; i--)
	{
		if (i == Fdof)
		{
			FX_VectAdd(F[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);
			to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, F[i], n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);

		}
		else
		{
			FX_VectAdd(F[i], dyn->m_Link_F_inBase[i + 1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], dyn->m_Link_N_inBase[i + 1], dyn->m_Link_N_inBase[i]);

			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_JointPG[i + 1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_JointPG[i + 1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_JointPG[i + 1][2][3] - kine->m_JointPG[i][2][3]);
			Vect3 n_nxt;
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			if (i >= AxisSerial)
			{
				Vect3 to_mcp_v;
				to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
				to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
				to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);
				Vect3 n_mcp;
				FX_VectCross(to_mcp_v, F[i], n_mcp);
				FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
			}
		}

		ret_Tau[i] = kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0]
			+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1]
			+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_Centri_Base_Fix(FX_INT32L RobotSerial, Matrix7 ret_CentriBase)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L i, j;
	FX_DOUBLE tau[7] = { 0 };
	for (i = 0; i < dof; i++) {

		FX_Robot_CalSigOmg_Fix(RobotSerial, i, tau);
		for (j = 0; j < 7; j++) {
			ret_CentriBase[j][i] = tau[j];
		}
	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_Centri_Mat_Fix(FX_INT32L RobotSerial, Matrix7 in_CentriBase, Vect7 in_AngVel, Matrix7 ret_CentriMat)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L j, i;
	FX_DOUBLE qd[7] = { 0 };
	for ( i = 0; i < dof; i++)
	{
		qd[i] = in_AngVel[i] * FXARM_D2R;
	}
	
	for (i = 0; i < dof; i++) {
		for (j = 0; j < 7; j++) {
			ret_CentriMat[i][j] = in_CentriBase[i][j]*qd[j];
		}
	}
	return FX_TRUE;
}


FX_BOOL  FX_Robot_CalDualOmg_Fix(FX_INT32L RobotSerial, FX_INT32L AxisSerial1, FX_INT32L AxisSerial2, Vect7 ret_Tau)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF - 1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}
	if (AxisSerial1 < 0 || AxisSerial1 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial2 < 0 || AxisSerial2 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial1 >= AxisSerial2)
	{
		return FX_FALSE;
	}


	Vect3 omg1;
	omg1[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][0];
	omg1[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][1];
	omg1[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][2];
	Vect3 omg2;
	omg2[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][0];
	omg2[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][1];
	omg2[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][2];
	Vect3 omgd;
	FX_VectCross(omg1, omg2, omgd);

	Vect3 F[8];
	Vect3 N[8];

	for (i = 0; i < dof; i++)
	{
		if (i < AxisSerial2)
		{
			F[i][0] = 0;
			F[i][1] = 0;
			F[i][2] = 0;

			N[i][0] = 0;
			N[i][1] = 0;
			N[i][2] = 0;
		}
		else
		{
			Vect3 _to_mcp;
			_to_mcp[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[AxisSerial2][0][3]);
			_to_mcp[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[AxisSerial2][1][3]);
			_to_mcp[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[AxisSerial2][2][3]);
			Vect3 acc;
			FX_VectCross(omgd, _to_mcp, acc);
			

			Vect3 a1;
			Vect3 a;

			FX_VectCross(omg1, _to_mcp, a1);
			FX_VectCross(omg2, a1, a);
			FX_VectAddToA(acc, a);
			FX_VectCross(omg2, _to_mcp, a1);
			FX_VectCross(omg1, a1, a);
			FX_VectAddToA(acc, a);

			F[i][0] = (acc[0]) * dyn->m_JntMass[i];
			F[i][1] = (acc[1]) * dyn->m_JntMass[i];
			F[i][2] = (acc[2]) * dyn->m_JntMass[i];



			FX_MMV3(dyn->m_JntInertia_inBase[i], omgd, N[i]);
			Vect3 t_t;
			Vect3 t;
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg1, t_t);
			FX_VectCross(omg2, t_t, t);
			FX_VectAddToA(N[i], t);
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg2, t_t);
			FX_VectCross(omg1, t_t, t);
			FX_VectAddToA(N[i], t);
		}
	}

	Vect3 F_Tool;
	Vect3 N_Tool;
	{
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		Vect3 a1;
		Vect3 a;
		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		FX_VectAddToA(acc, a);
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		FX_VectAddToA(acc, a);

		F_Tool[0] = (acc[0]) * dyn->m_ToolMass;
		F_Tool[1] = (acc[1]) * dyn->m_ToolMass;
		F_Tool[2] = (acc[2]) * dyn->m_ToolMass;

		FX_MMV3(dyn->m_ToolInertia_inBase, omgd, N_Tool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_ToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_ToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_Tool, t);
	}


	Vect3 F_NTool;
	Vect3 N_NTool;

	if (dyn->m_NToolTag == FX_TRUE)
	{

		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		Vect3 a1;
		Vect3 a;
		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		FX_VectAddToA(acc, a);
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		FX_VectAddToA(acc, a);

		F_NTool[0] = -(acc[0]) * dyn->m_NToolMass;
		F_NTool[1] = -(acc[1]) * dyn->m_NToolMass;
		F_NTool[2] = -(acc[2]) * dyn->m_NToolMass;

		FX_MMV3(dyn->m_NToolInertia_inBase, omgd, N_NTool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_NToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_NToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_NTool, t);
	}

	Vect3 flange_f;
	{
		flange_f[0] = F_Tool[0];
		flange_f[1] = F_Tool[1];
		flange_f[2] = F_Tool[2];
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, F_NTool);
		}
	}
	Vect3 flange_n;
	{
		flange_n[0] = N_Tool[0];
		flange_n[1] = N_Tool[1];
		flange_n[2] = N_Tool[2];

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, F_Tool, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, N_NTool);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, F_NTool, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for (i = Fdof; i >= 0; i--)
	{
		if (i == Fdof)
		{
			FX_VectAdd(F[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);
			to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, F[i], n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);

		}
		else
		{
			FX_VectAdd(F[i], dyn->m_Link_F_inBase[i + 1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], dyn->m_Link_N_inBase[i + 1], dyn->m_Link_N_inBase[i]);

			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_JointPG[i + 1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_JointPG[i + 1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_JointPG[i + 1][2][3] - kine->m_JointPG[i][2][3]);
			Vect3 n_nxt;
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			if (i >= AxisSerial2)
			{
				Vect3 to_mcp_v;
				to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
				to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
				to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);
				Vect3 n_mcp;
				FX_VectCross(to_mcp_v, F[i], n_mcp);
				FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
			}
		}

		ret_Tau[i] = kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0]
			+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1]
			+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}
	return FX_TRUE;
}


FX_BOOL  FX_Robot_CalDualOmg_Fix2(FX_INT32L RobotSerial, FX_INT32L AxisSerial1, FX_INT32L AxisSerial2, Vect7 ret_Tau)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF - 1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}
	if (AxisSerial1 < 0 || AxisSerial1 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial2 < 0 || AxisSerial2 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial1  >= AxisSerial2)
	{
		return FX_FALSE;
	}


	Vect3 omg1;
	omg1[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][0];
	omg1[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][1];
	omg1[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][2];
	Vect3 omg2;
	omg2[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][0];
	omg2[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][1];
	omg2[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][2];
	Vect3 omgd;
	FX_VectCross(omg1,omg2,omgd);

	Vect3 F[8];
	Vect3 N[8];

	for (i = 0; i < dof; i++)
	{
		if (i < AxisSerial2)
		{
			F[i][0] = 0;
			F[i][1] = 0;
			F[i][2] = 0;

			N[i][0] = 0;
			N[i][1] = 0;
			N[i][2] = 0;
		}
		else
		{
			Vect3 _to_mcp;
			_to_mcp[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[AxisSerial2][0][3]);
			_to_mcp[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[AxisSerial2][1][3]);
			_to_mcp[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[AxisSerial2][2][3]);
			Vect3 acc;
			FX_VectCross(omgd, _to_mcp, acc);
			F[i][0] = (acc[0]) * dyn->m_JntMass[i];
			F[i][1] = (acc[1]) * dyn->m_JntMass[i];
			F[i][2] = (acc[2]) * dyn->m_JntMass[i];
			
			Vect3 a1;
			Vect3 a;

			FX_VectCross(omg1, _to_mcp, a1);
			FX_VectCross(omg2, a1, a);
			FX_VectAddToA(F[i], a);
			FX_VectCross(omg2, _to_mcp, a1);
			FX_VectCross(omg1, a1, a);
			FX_VectAddToA(F[i], a);


			FX_MMV3(dyn->m_JntInertia_inBase[i], omgd, N[i]);
			Vect3 t_t;
			Vect3 t;
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg1, t_t);
			FX_VectCross(omg2, t_t, t);
			FX_VectAddToA(N[i],t);
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg2, t_t);
			FX_VectCross(omg1, t_t, t);
			FX_VectAddToA(N[i], t);
		}
	}

	Vect3 F_Tool;
	Vect3 N_Tool;
	{
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		F_Tool[0] = (acc[0]) * dyn->m_ToolMass;
		F_Tool[1] = (acc[1]) * dyn->m_ToolMass;
		F_Tool[2] = (acc[2]) * dyn->m_ToolMass;


		Vect3 a1;
		Vect3 a;

		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		FX_VectAddToA(F_Tool, a);
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		FX_VectAddToA(F_Tool, a);




		FX_MMV3(dyn->m_ToolInertia_inBase, omgd, N_Tool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_ToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_ToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_Tool, t);
	}


	Vect3 F_NTool;
	Vect3 N_NTool;

	if (dyn->m_NToolTag == FX_TRUE)
	{
		
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		F_NTool[0] = -(acc[0]) * dyn->m_NToolMass;
		F_NTool[1] = -(acc[1]) * dyn->m_NToolMass;
		F_NTool[2] = -(acc[2]) * dyn->m_NToolMass;

		Vect3 a1;
		Vect3 a;
		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		F_NTool[0] = -a[0];
		F_NTool[1] = -a[1];
		F_NTool[2] = -a[2];
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		F_NTool[0] = -a[0];
		F_NTool[1] = -a[1];
		F_NTool[2] = -a[2];

		FX_MMV3(dyn->m_NToolInertia_inBase, omgd, N_NTool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_NToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_NToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_NTool, t);
	}

	Vect3 flange_f;
	{
		flange_f[0] = F_Tool[0];
		flange_f[1] = F_Tool[1];
		flange_f[2] = F_Tool[2];
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, F_NTool);
		}
	}
	Vect3 flange_n;
	{
		flange_n[0] = N_Tool[0];
		flange_n[1] = N_Tool[1];
		flange_n[2] = N_Tool[2];

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, F_Tool, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, N_NTool);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, F_NTool, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for (i = Fdof; i >= 0; i--)
	{
		if (i == Fdof)
		{
			FX_VectAdd(F[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);
			to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, F[i], n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);

		}
		else
		{
			FX_VectAdd(F[i], dyn->m_Link_F_inBase[i + 1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], dyn->m_Link_N_inBase[i + 1], dyn->m_Link_N_inBase[i]);

			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_JointPG[i + 1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_JointPG[i + 1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_JointPG[i + 1][2][3] - kine->m_JointPG[i][2][3]);
			Vect3 n_nxt;
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			if (i >= AxisSerial2)
			{
				Vect3 to_mcp_v;
				to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
				to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
				to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);
				Vect3 n_mcp;
				FX_VectCross(to_mcp_v, F[i], n_mcp);
				FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
			}
		}

		ret_Tau[i] = kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0]
			+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1]
			+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_Coriolis_Mat_Fix(FX_INT32L RobotSerial, Matrix7 in_ColiosBase[7], Vect7 in_AngVel, Matrix7 ret_ColiosMat)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L i, j, k;
	FX_DOUBLE qd[7] = { 0 };

	for (i = 0; i < dof; i++) 
	{
		qd[i] = in_AngVel[i] * FXARM_D2R;
		for (j = 0; j < dof; j++)
		{
			ret_ColiosMat[i][j] = 0;
		}
	}

	for (i = 0; i < dof; i++) {

		for (j = i + 1; j < dof; j++)
		{
			for (k = 0; k < dof; k++)
			{
				ret_ColiosMat[k][i] += in_ColiosBase[i][j][k] * qd[j];
				ret_ColiosMat[k][j] += in_ColiosBase[i][j][k] * qd[i];
			}
		}
	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_Coriolis_Base_Fix(FX_INT32L RobotSerial, Matrix7 ret_ColiosBase[7])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L i, j ,k;
	FX_DOUBLE tau[7] = { 0 };
	for (i = 0; i < dof; i++) {

		for ( j = i+1; j < dof; j++)
		{
			FX_Robot_CalDualOmg_Fix(RobotSerial, i, j, tau);
			for ( k = 0; k < dof; k++)
			{
				ret_ColiosBase[i][j][k] = tau[k] * 0.5;
			}
		}
		
	}
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_ID_Fix(FX_INT32L RobotSerial, Vect7 qd, Vect7 qdd, Vect6 ex_fn, Vect7 ret_tau)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF-1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}

	for ( i = 0; i < pRobot->m_RobotDOF; i++)
	{
		if (i == 0)
		{
			FX_DOUBLE omg_in_arc = qd[i] * FXARM_D2R;
			dyn->m_OMG[i][0] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][0];
			dyn->m_OMG[i][1] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][1];
			dyn->m_OMG[i][2] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][2];

			FX_DOUBLE omgd_in_arc = qdd[i] * FXARM_D2R;
			dyn->m_OMGd[i][0] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][0];
			dyn->m_OMGd[i][1] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][1];
			dyn->m_OMGd[i][2] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][2];

			dyn->m_Acc[i][0] = dyn->m_CalGravity[0];
			dyn->m_Acc[i][1] = dyn->m_CalGravity[1];
			dyn->m_Acc[i][2] = dyn->m_CalGravity[2];
		}
		else
		{
			FX_DOUBLE omg_in_arc = qd[i] * FXARM_D2R;
			Vect3 cur_rot_omg;
			cur_rot_omg[0] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][0];
			cur_rot_omg[1] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][1];
			cur_rot_omg[2] = omg_in_arc * dyn->m_JntRotAxisDir_inBase[i][2];

			dyn->m_OMG[i][0] = cur_rot_omg[0] + dyn->m_OMG[i-1][0];
			dyn->m_OMG[i][1] = cur_rot_omg[1] + dyn->m_OMG[i-1][1];
			dyn->m_OMG[i][2] = cur_rot_omg[2] + dyn->m_OMG[i-1][2];

			Vect3 cur_rot_omg_ind_omgd;
			FX_VectCross(dyn->m_OMG[i - 1], cur_rot_omg, cur_rot_omg_ind_omgd);
			FX_DOUBLE omgd_in_arc = qdd[i] * FXARM_D2R;
			dyn->m_OMGd[i][0] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][0] + cur_rot_omg_ind_omgd[0] + dyn->m_OMGd[i - 1][0];
			dyn->m_OMGd[i][1] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][1] + cur_rot_omg_ind_omgd[1] + dyn->m_OMGd[i - 1][1];
			dyn->m_OMGd[i][2] = omgd_in_arc * dyn->m_JntRotAxisDir_inBase[i][2] + cur_rot_omg_ind_omgd[2] + dyn->m_OMGd[i - 1][2];

			Vect3 jnt_base_to_pre;
			jnt_base_to_pre[0] =0.001 * (kine->m_JointPG[i][0][3] - kine->m_JointPG[i - 1][0][3]);
			jnt_base_to_pre[1] =0.001 * (kine->m_JointPG[i][1][3] - kine->m_JointPG[i - 1][1][3]);
			jnt_base_to_pre[2] =0.001 * (kine->m_JointPG[i][2][3] - kine->m_JointPG[i - 1][2][3]);

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[i - 1], jnt_base_to_pre, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[i - 1], jnt_base_to_pre, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[i - 1], omg_ind_acc_t, omg_ind_acc);

			dyn->m_Acc[i][0] = (dyn->m_Acc[i - 1][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_Acc[i][1] = (dyn->m_Acc[i - 1][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_Acc[i][2] = (dyn->m_Acc[i - 1][2] + omg_ind_acc[2] + omgd_ind_acc[2]);
		}
		{
			Vect3 mcp_to_jnt_base;
			mcp_to_jnt_base[0] =0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			mcp_to_jnt_base[1] =0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			mcp_to_jnt_base[2] =0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[i], mcp_to_jnt_base, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[i], mcp_to_jnt_base, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[i], omg_ind_acc_t, omg_ind_acc);

			dyn->m_AccMC[i][0] = (dyn->m_Acc[i][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_AccMC[i][1] = (dyn->m_Acc[i][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_AccMC[i][2] = (dyn->m_Acc[i][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

			dyn->m_JntF_inBase[i][0] = dyn->m_JntMass[i] * dyn->m_AccMC[i][0];
			dyn->m_JntF_inBase[i][1] = dyn->m_JntMass[i] * dyn->m_AccMC[i][1];
			dyn->m_JntF_inBase[i][2] = dyn->m_JntMass[i] * dyn->m_AccMC[i][2];

			Vect3 omgd_ind_n;
			FX_MMV3(dyn->m_JntInertia_inBase[i], dyn->m_OMGd[i], omgd_ind_n);
			Vect3 omg_ind_n;
			Vect3 omg_ind_nt;
			FX_MMV3(dyn->m_JntInertia_inBase[i], dyn->m_OMG[i], omg_ind_nt);
			FX_VectCross(dyn->m_OMG[i], omg_ind_nt, omg_ind_n);
			FX_VectAdd(omg_ind_n, omgd_ind_n, dyn->m_JntN_inBase[i]);
		}
	}


	{
		if(dyn->m_NToolTag == FX_TRUE)
		{
			Vect3 tool_mcp_to_jnt_base;
			tool_mcp_to_jnt_base[0] =0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[Fdof][0][3]);
			tool_mcp_to_jnt_base[1] =0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[Fdof][1][3]);
			tool_mcp_to_jnt_base[2] =0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[Fdof][2][3]);

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[Fdof], tool_mcp_to_jnt_base, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[Fdof], tool_mcp_to_jnt_base, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[Fdof], omg_ind_acc_t, omg_ind_acc);

			dyn->m_NToolAccMC[0] = (dyn->m_Acc[Fdof][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_NToolAccMC[1] = (dyn->m_Acc[Fdof][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_NToolAccMC[2] = (dyn->m_Acc[Fdof][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

			dyn->m_NToolDynF_inBase[0] = dyn->m_NToolAccMC[0] * dyn->m_NToolMass;
			dyn->m_NToolDynF_inBase[1] = dyn->m_NToolAccMC[1] * dyn->m_NToolMass;
			dyn->m_NToolDynF_inBase[2] = dyn->m_NToolAccMC[2] * dyn->m_NToolMass;

			Vect3 Nomgd;
			FX_MMV3(dyn->m_NToolInertia_inBase, dyn->m_OMGd[Fdof], Nomgd);
			Vect3 Nomgt;
			Vect3 Nomg;
			FX_MMV3(dyn->m_NToolInertia_inBase, dyn->m_OMGd[Fdof], Nomgt);
			FX_VectCross(dyn->m_OMGd[Fdof], Nomgt, Nomg);

			FX_VectAdd(Nomgd, Nomg, dyn->m_NToolDynN_inBase);

			dyn->m_NToolDynF_inBase[0] = -dyn->m_NToolDynF_inBase[0];
			dyn->m_NToolDynF_inBase[1] = -dyn->m_NToolDynF_inBase[1];
			dyn->m_NToolDynF_inBase[2] = -dyn->m_NToolDynF_inBase[2];

			dyn->m_NToolDynN_inBase[0] = -dyn->m_NToolDynN_inBase[0];
			dyn->m_NToolDynN_inBase[1] = -dyn->m_NToolDynN_inBase[1];
			dyn->m_NToolDynN_inBase[2] = -dyn->m_NToolDynN_inBase[2];
		}
		{
			Vect3 tool_mcp_to_jnt_base;
			tool_mcp_to_jnt_base[0] =0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[Fdof][0][3]);
			tool_mcp_to_jnt_base[1] =0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[Fdof][1][3]);
			tool_mcp_to_jnt_base[2] =0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[Fdof][2][3]);

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[Fdof], tool_mcp_to_jnt_base, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[Fdof], tool_mcp_to_jnt_base, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[Fdof], omg_ind_acc_t, omg_ind_acc);

			dyn->m_ToolAccMC[0] = (dyn->m_Acc[Fdof][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_ToolAccMC[1] = (dyn->m_Acc[Fdof][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_ToolAccMC[2] = (dyn->m_Acc[Fdof][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

			dyn->m_ToolDynF_inBase[0] = dyn->m_ToolAccMC[0] * dyn->m_ToolMass;
			dyn->m_ToolDynF_inBase[1] = dyn->m_ToolAccMC[1] * dyn->m_ToolMass;
			dyn->m_ToolDynF_inBase[2] = dyn->m_ToolAccMC[2] * dyn->m_ToolMass;


			Vect3 omgd;
			FX_MMV3(dyn->m_ToolInertia_inBase, dyn->m_OMGd[Fdof], omgd);
			Vect3 omgt;
			Vect3 omg;
			FX_MMV3(dyn->m_ToolInertia_inBase, dyn->m_OMGd[Fdof], omgt);
			FX_VectCross(dyn->m_OMGd[Fdof], omgt, omg);

			FX_VectAdd(omgd, omg, dyn->m_ToolDynN_inBase);

		}
	}

	Vect3 Tcp_ExF_inBase;
	Vect3 Tcp_ExN_inBase;
	Tcp_ExF_inBase[0] = ex_fn[0];
	Tcp_ExF_inBase[1] = ex_fn[1];
	Tcp_ExF_inBase[2] = ex_fn[2];

	Tcp_ExN_inBase[0] = ex_fn[3];
	Tcp_ExN_inBase[1] = ex_fn[4];
	Tcp_ExN_inBase[2] = ex_fn[5];


	Vect3 flange_f;
	{
		FX_VectAdd(dyn->m_ToolDynF_inBase, Tcp_ExF_inBase, flange_f);
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, dyn->m_NToolDynF_inBase);
		}
	}
	Vect3 flange_n;
	{
		FX_VectAdd(dyn->m_ToolDynN_inBase, Tcp_ExN_inBase, flange_n);
		Vect3 tcp_2_flange_in_w;
		tcp_2_flange_in_w[0] =0.001 * (kine->m_TCP[0][3] - kine->m_FlangeTip[0][3]);
		tcp_2_flange_in_w[1] =0.001 * (kine->m_TCP[1][3] - kine->m_FlangeTip[1][3]);
		tcp_2_flange_in_w[2] =0.001 * (kine->m_TCP[2][3] - kine->m_FlangeTip[2][3]);

		Vect3 force_lead_n;
		FX_VectCross(tcp_2_flange_in_w, Tcp_ExF_inBase, force_lead_n);
		FX_VectAddToA(flange_n, force_lead_n);

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] =0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] =0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] =0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, dyn->m_ToolDynF_inBase, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, dyn->m_NToolDynN_inBase);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] =0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] =0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] =0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, dyn->m_NToolDynF_inBase, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for ( i = Fdof; i >=0; i--)
	{
		if(i == Fdof)
		{
			FX_VectAdd(dyn->m_JntF_inBase[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(dyn->m_JntN_inBase[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] =0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] =0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] =0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);

			to_mcp_v[0] =0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] =0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] =0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, dyn->m_JntF_inBase[i],n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
		
		}
		else
		{
			FX_VectAdd(dyn->m_JntF_inBase[i], dyn->m_Link_F_inBase[i+1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(dyn->m_JntN_inBase[i], dyn->m_Link_N_inBase[i+1], dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] =0.001 * (kine->m_JointPG[i+1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] =0.001 * (kine->m_JointPG[i+1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] =0.001 * (kine->m_JointPG[i+1][2][3] - kine->m_JointPG[i][2][3]);

			to_mcp_v[0] =0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] =0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] =0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, dyn->m_JntF_inBase[i], n_mcp);
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
		}


		ret_tau[i]	= kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0] 
					+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1] 
					+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}

	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_ID_Folt(FX_INT32L RobotSerial, Vect7 q, Vect7 qd, Vect7 qdd, Vect3 base_omg, Vect3 base_omgd, Vect3 base_grv, Vect6 ex_fn, Vect7 ret_tau)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];

	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fpos = dof - 1;
	if (Fpos < 0)
	{
		Fpos = 0;
	}
	Matrix4   pg;
	FX_Robot_Kine_FK(RobotSerial, q, pg);

	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;

	Vect3 t_base_omg;
	Vect3 t_base_omgd;
	FX_Vect3AToB(base_omg, t_base_omg);
	FX_Vect3AToB(base_omgd, t_base_omgd);

	FX_Vect3AToB(base_omg, dyn->m_OMG[0]);
	FX_Vect3AToB(base_omgd, dyn->m_OMGd[0]);

	FX_Vect3AToB(base_grv, dyn->m_Acc[0]);

	for ( i = 0; i < dof; i++)
	{
		Vect3 cur_axis_omg;
		cur_axis_omg[0] = qd[i] * FXARM_D2R * kine->m_JointPG[i][0][2];
		cur_axis_omg[1] = qd[i] * FXARM_D2R * kine->m_JointPG[i][1][2];
		cur_axis_omg[2] = qd[i] * FXARM_D2R * kine->m_JointPG[i][2][2];
		if (i == 0)
		{
			dyn->m_OMG[i][0] += cur_axis_omg[0];
			dyn->m_OMG[i][1] += cur_axis_omg[1];
			dyn->m_OMG[i][2] += cur_axis_omg[2];
		}
		else
		{

			dyn->m_OMG[i][0] = dyn->m_OMG[i - 1][0] + cur_axis_omg[0];
			dyn->m_OMG[i][1] = dyn->m_OMG[i - 1][1] + cur_axis_omg[1];
			dyn->m_OMG[i][2] = dyn->m_OMG[i - 1][2] + cur_axis_omg[2];
		}

		Vect3 cur_axis_omgd;
		cur_axis_omgd[0] = qdd[i] * FXARM_D2R * kine->m_JointPG[i][0][2];
		cur_axis_omgd[1] = qdd[i] * FXARM_D2R * kine->m_JointPG[i][1][2];
		cur_axis_omgd[2] = qdd[i] * FXARM_D2R * kine->m_JointPG[i][2][2];

		if (i == 0)
		{
			Vect3 vel_ind_acc;
			FX_VectCross(t_base_omg, cur_axis_omg, vel_ind_acc);
			dyn->m_OMGd[i][0] += (vel_ind_acc[0] + cur_axis_omgd[0]);
			dyn->m_OMGd[i][1] += (vel_ind_acc[1] + cur_axis_omgd[1]);
			dyn->m_OMGd[i][2] += (vel_ind_acc[2] + cur_axis_omgd[2]);
		}
		else
		{
			Vect3 vel_ind_acc;
			FX_VectCross(dyn->m_OMG[i - 1], cur_axis_omg, vel_ind_acc);

			dyn->m_OMGd[i][0] = dyn->m_OMG[i - 1][0] + cur_axis_omg[0] + vel_ind_acc[0];
			dyn->m_OMGd[i][1] = dyn->m_OMGd[i - 1][1] + cur_axis_omg[1] + vel_ind_acc[1];
			dyn->m_OMGd[i][2] = dyn->m_OMGd[i - 1][2] + cur_axis_omg[2] + vel_ind_acc[2];
		}

		if (i == 0)
		{
			Vect3 jnt_base_to_pre;
			jnt_base_to_pre[0] = kine->m_JointPG[0][0][3];
			jnt_base_to_pre[1] = kine->m_JointPG[0][1][3];
			jnt_base_to_pre[2] = kine->m_JointPG[0][2][3];

			Vect3 omgd_ind_acc;
			FX_VectCross(t_base_omgd, jnt_base_to_pre, omgd_ind_acc);
			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(t_base_omg, jnt_base_to_pre, omg_ind_acc_t);
			FX_VectCross(t_base_omg, omg_ind_acc_t, omg_ind_acc);

			dyn->m_Acc[i][0] += (omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_Acc[i][1] += (omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_Acc[i][2] += (omg_ind_acc[2] + omgd_ind_acc[2]);


		}
		else
		{
			Vect3 jnt_base_to_pre;
			jnt_base_to_pre[0] = kine->m_JointPG[i][0][3] - kine->m_JointPG[i - 1][0][3];
			jnt_base_to_pre[1] = kine->m_JointPG[i][1][3] - kine->m_JointPG[i - 1][1][3];
			jnt_base_to_pre[2] = kine->m_JointPG[i][2][3] - kine->m_JointPG[i - 1][2][3];

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[i - 1], jnt_base_to_pre, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[i - 1], jnt_base_to_pre, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[i - 1], omg_ind_acc_t, omg_ind_acc);

			dyn->m_Acc[i][0] = (dyn->m_Acc[i - 1][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_Acc[i][1] = (dyn->m_Acc[i - 1][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_Acc[i][2] = (dyn->m_Acc[i - 1][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

		}

		{
			Vect3 mcp_to_jnt_base;
			
			FX_PGVectMap(kine->m_JointPG[i], dyn->m_JntMCP[i], mcp_to_jnt_base);

			Vect3 omgd_ind_acc;
			FX_VectCross(dyn->m_OMGd[i], mcp_to_jnt_base, omgd_ind_acc);

			Vect3 omg_ind_acc;
			Vect3 omg_ind_acc_t;
			FX_VectCross(dyn->m_OMG[i], mcp_to_jnt_base, omg_ind_acc_t);
			FX_VectCross(dyn->m_OMG[i], omg_ind_acc_t, omg_ind_acc);

			dyn->m_AccMC[i][0] = (dyn->m_Acc[i][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
			dyn->m_AccMC[i][1] = (dyn->m_Acc[i][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
			dyn->m_AccMC[i][2] = (dyn->m_Acc[i][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

		}

		dyn->m_JntF_inBase[i][0] = dyn->m_AccMC[i][0] * dyn->m_JntMass[i];
		dyn->m_JntF_inBase[i][1] = dyn->m_AccMC[i][1] * dyn->m_JntMass[i];
		dyn->m_JntF_inBase[i][2] = dyn->m_AccMC[i][2] * dyn->m_JntMass[i];

		Vect3 omg_in_joint;
		Vect3 omg_d_in_joint;
		FX_PGVectMapInv(kine->m_JointPG[i], dyn->m_OMG[i], omg_in_joint);
		FX_PGVectMapInv(kine->m_JointPG[i], dyn->m_OMGd[i], omg_d_in_joint);
		Vect3 Nomgd;
		FX_MMV3(dyn->m_JntInertia[i], omg_d_in_joint, Nomgd);
		Vect3 Nomgt; 
		Vect3 Nomg;
		FX_MMV3(dyn->m_JntInertia[i], omg_in_joint, Nomgt);
		FX_VectCross(omg_in_joint, Nomgt, Nomg);


		Vect3 jntn;
		jntn[0] = Nomgd[0] + Nomg[0];
		jntn[1] = Nomgd[1] + Nomg[1];
		jntn[2] = Nomgd[2] + Nomg[2];

		FX_PGVectMap(kine->m_JointPG[i], jntn, dyn->m_JntN_inBase[i]);
	}


	{
		Vect3 tool_mcp_pos;
		FX_PGPointMap(kine->m_FlangeTip, dyn->m_ToolMCP, tool_mcp_pos);
		Vect3 tool_mcp_to_jnt_base;
		
		tool_mcp_to_jnt_base[0] = tool_mcp_pos[0] - kine->m_JointPG[Fpos][0][3];
		tool_mcp_to_jnt_base[1] = tool_mcp_pos[1] - kine->m_JointPG[Fpos][1][3];
		tool_mcp_to_jnt_base[2] = tool_mcp_pos[2] - kine->m_JointPG[Fpos][2][3];
	

		Vect3 omgd_ind_acc;
		FX_VectCross(dyn->m_OMGd[Fpos], tool_mcp_to_jnt_base, omgd_ind_acc);

		Vect3 omg_ind_acc;
		Vect3 omg_ind_acc_t;
		FX_VectCross(dyn->m_OMG[Fpos], tool_mcp_to_jnt_base, omg_ind_acc_t);
		FX_VectCross(dyn->m_OMG[Fpos], omg_ind_acc_t, omg_ind_acc);

		dyn->m_ToolAccMC[0] = (dyn->m_Acc[Fpos][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
		dyn->m_ToolAccMC[1] = (dyn->m_Acc[Fpos][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
		dyn->m_ToolAccMC[2] = (dyn->m_Acc[Fpos][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

		dyn->m_ToolDynF_inBase[0] = dyn->m_ToolAccMC[0] * dyn->m_ToolMass;
		dyn->m_ToolDynF_inBase[1] = dyn->m_ToolAccMC[1] * dyn->m_ToolMass;
		dyn->m_ToolDynF_inBase[2] = dyn->m_ToolAccMC[2] * dyn->m_ToolMass;


		Vect3 omg_in_joint;
		Vect3 omg_d_in_joint;
		FX_PGVectMapInv(kine->m_JointPG[Fpos], dyn->m_OMG[Fpos], omg_in_joint);
		FX_PGVectMapInv(kine->m_JointPG[Fpos], dyn->m_OMGd[Fpos], omg_d_in_joint);
		Vect3 Nomgd;
		FX_MMV3(dyn->m_ToolInertia, omg_d_in_joint, Nomgd);
		Vect3 Nomgt;
		Vect3 Nomg;
		FX_MMV3(dyn->m_ToolInertia, omg_in_joint, Nomgt);
		FX_VectCross(omg_in_joint, Nomgt, Nomg);
		Vect3 jntn;
		jntn[0] = Nomgd[0] + Nomg[0];
		jntn[1] = Nomgd[1] + Nomg[1];
		jntn[2] = Nomgd[2] + Nomg[2];
		FX_PGVectMap(kine->m_JointPG[Fpos], jntn, dyn->m_ToolDynN_inBase);
	}

	{
		Vect3 tool_mcp_pos;
		FX_PGPointMap(kine->m_FlangeTip, dyn->m_NToolMCP, tool_mcp_pos);
		Vect3 tool_mcp_to_jnt_base;

		tool_mcp_to_jnt_base[0] = tool_mcp_pos[0] - kine->m_JointPG[Fpos][0][3];
		tool_mcp_to_jnt_base[1] = tool_mcp_pos[1] - kine->m_JointPG[Fpos][1][3];
		tool_mcp_to_jnt_base[2] = tool_mcp_pos[2] - kine->m_JointPG[Fpos][2][3];


		Vect3 omgd_ind_acc;
		FX_VectCross(dyn->m_OMGd[Fpos], tool_mcp_to_jnt_base, omgd_ind_acc);

		Vect3 omg_ind_acc;
		Vect3 omg_ind_acc_t;
		FX_VectCross(dyn->m_OMG[Fpos], tool_mcp_to_jnt_base, omg_ind_acc_t);
		FX_VectCross(dyn->m_OMG[Fpos], omg_ind_acc_t, omg_ind_acc);

		dyn->m_NToolAccMC[0] = (dyn->m_Acc[Fpos][0] + omg_ind_acc[0] + omgd_ind_acc[0]);
		dyn->m_NToolAccMC[1] = (dyn->m_Acc[Fpos][1] + omg_ind_acc[1] + omgd_ind_acc[1]);
		dyn->m_NToolAccMC[2] = (dyn->m_Acc[Fpos][2] + omg_ind_acc[2] + omgd_ind_acc[2]);

		dyn->m_NToolDynF_inBase[0] = dyn->m_NToolAccMC[0] * dyn->m_NToolMass;
		dyn->m_NToolDynF_inBase[1] = dyn->m_NToolAccMC[1] * dyn->m_NToolMass;
		dyn->m_NToolDynF_inBase[2] = dyn->m_NToolAccMC[2] * dyn->m_NToolMass;


		Vect3 omg_in_joint;
		Vect3 omg_d_in_joint;
		FX_PGVectMapInv(kine->m_JointPG[Fpos], dyn->m_OMG[Fpos], omg_in_joint);
		FX_PGVectMapInv(kine->m_JointPG[Fpos], dyn->m_OMGd[Fpos], omg_d_in_joint);
		Vect3 Nomgd;
		FX_MMV3(dyn->m_NToolInertia, omg_d_in_joint, Nomgd);
		Vect3 Nomgt;
		Vect3 Nomg;
		FX_MMV3(dyn->m_NToolInertia, omg_in_joint, Nomgt);
		FX_VectCross(omg_in_joint, Nomgt, Nomg);
		Vect3 jntn;
		jntn[0] = Nomgd[0] + Nomg[0];
		jntn[1] = Nomgd[1] + Nomg[1];
		jntn[2] = Nomgd[2] + Nomg[2];
		FX_PGVectMap(kine->m_JointPG[Fpos], jntn, dyn->m_NToolDynN_inBase);

		dyn->m_NToolDynF_inBase[0] = -dyn->m_NToolDynF_inBase[0];
		dyn->m_NToolDynF_inBase[1] = -dyn->m_NToolDynF_inBase[1];
		dyn->m_NToolDynF_inBase[2] = -dyn->m_NToolDynF_inBase[2];

		dyn->m_NToolDynN_inBase[0] = -dyn->m_NToolDynN_inBase[0];
		dyn->m_NToolDynN_inBase[1] = -dyn->m_NToolDynN_inBase[1];
		dyn->m_NToolDynN_inBase[2] = -dyn->m_NToolDynN_inBase[2];
	}



}



FX_BOOL  FX_Robot_Dyna_Map_DynPara_B2A(PosGes A, PosGes B, Matrix3 I_in_b, Vect3 Mcp_in_b, Matrix3 ret_I_in_a, Vect3 ret_Mcp_in_a)
{
	PosGes B2A;
	PosGes invA;
	FX_PGMatrixInv(A, invA);
	FX_PGMult(invA, B, B2A);
	FX_PGPointMap(B2A, Mcp_in_b, ret_Mcp_in_a);
	Matrix3 B2AGes;
	FX_PGGetGes(B2A, B2AGes);
	InertiaTran(I_in_b, B2AGes, ret_I_in_a);
	return FX_TRUE;
}


FX_BOOL  FX_Robot_Kine_GetLinkPG(FX_INT32L RobotSerial, FX_DOUBLE PG[7][4][4])
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_KineBase* kine = &pRobot->m_KineBase;

	FX_INT32L i;
	for ( i = 0; i < 7; i++)
	{
		FX_M44Copy(kine->m_JointPG[i], PG[i]);
	}
//	FX_M44Copy(kine->m_FlangeTip, PG[7]);
	return FX_TRUE;
}

FX_BOOL  FX_Robot_Dyna_Flt_BaseSet(FX_INT32L RobotSerial, Matrix3 in_BaseGes, Vect3 in_BaseAcc, Vect3 in_BaseOmg, Vect3 in_BaseOmgD)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;

	dyn->m_BaseFloatationTag = FX_TRUE;
	FX_Vect3AToB(in_BaseAcc, dyn->m_BaseFloatationAcc);
	FX_Vect3AToB(in_BaseOmg, dyn->m_BaseFloatationOmg_Dir);
	FX_Vect3AToB(in_BaseOmgD, dyn->m_BaseFloatationOmgD_Dir);

	dyn->m_BaseFloatationOmg_Val = FX_Sqrt(in_BaseOmg[0] * in_BaseOmg[0] + in_BaseOmg[1] * in_BaseOmg[1] + in_BaseOmg[2] * in_BaseOmg[2]);
	dyn->m_BaseFloatationOmgD_Val = FX_Sqrt(in_BaseOmgD[0] * in_BaseOmgD[0] + in_BaseOmgD[1] * in_BaseOmgD[1] + in_BaseOmgD[2] * in_BaseOmgD[2]);
	if (dyn->m_BaseFloatationOmg_Val > 0.00001)
	{
		dyn->m_BaseFloatationOmg_Dir[0] = in_BaseOmg[0] / dyn->m_BaseFloatationOmg_Val;
		dyn->m_BaseFloatationOmg_Dir[1] = in_BaseOmg[1] / dyn->m_BaseFloatationOmg_Val;
		dyn->m_BaseFloatationOmg_Dir[2] = in_BaseOmg[2] / dyn->m_BaseFloatationOmg_Val;
		dyn->m_BaseFloatationOmg_Deg_Tag = FX_FALSE;
	}
	else
	{
		dyn->m_BaseFloatationOmg_Deg_Tag = FX_TRUE;
		dyn->m_BaseFloatationOmg_Dir[0] = 0;
		dyn->m_BaseFloatationOmg_Dir[1] = 0;
		dyn->m_BaseFloatationOmg_Dir[2] = 1;
		dyn->m_BaseFloatationOmg_Val = 0;
	}

	if (dyn->m_BaseFloatationOmgD_Val > 0.00001)
	{
		dyn->m_BaseFloatationOmgD_Dir[0] = in_BaseOmgD[0] / dyn->m_BaseFloatationOmgD_Val;
		dyn->m_BaseFloatationOmgD_Dir[1] = in_BaseOmgD[1] / dyn->m_BaseFloatationOmgD_Val;
		dyn->m_BaseFloatationOmgD_Dir[2] = in_BaseOmgD[2] / dyn->m_BaseFloatationOmgD_Val;
		dyn->m_BaseFloatationOmgD_Deg_Tag = FX_FALSE;
	}
	else
	{
		dyn->m_BaseFloatationOmgD_Deg_Tag = FX_TRUE;
		dyn->m_BaseFloatationOmgD_Dir[0] = 0;
		dyn->m_BaseFloatationOmgD_Dir[1] = 0;
		dyn->m_BaseFloatationOmgD_Dir[2] = 1;
		dyn->m_BaseFloatationOmgD_Val = 0;
	}

	FX_M33Copy(in_BaseGes, dyn->m_BaseFloatationGes);
	Matrix3 in_BaseGes_tr;
	FX_M33Trans(in_BaseGes, in_BaseGes_tr);
	Vect3  map_grv;
	FX_MMV3(in_BaseGes_tr, dyn->m_SettingGravity, map_grv);
	FX_VectAdd(dyn->m_SettingGravity, in_BaseAcc, dyn->m_CalGravity);
	return FX_TRUE;
}



FX_BOOL  FX_Robot_CalDualOmg_Flt(FX_INT32L RobotSerial, FX_INT32L AxisSerial1, FX_INT32L AxisSerial2, Vect8 ret_Tau)
{
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L i;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L Fdof = pRobot->m_RobotDOF - 1;
	if (Fdof < 0)
	{
		Fdof = 0;
	}
	if (AxisSerial1 < -1 || AxisSerial1 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial2 < 0 || AxisSerial2 >= dof)
	{
		return FX_FALSE;
	}

	if (AxisSerial1 >= AxisSerial2)
	{
		return FX_FALSE;
	}


	Vect3 omg1;
	
	if (AxisSerial1 == -1)
	{
		Vect3 basevdir;
		FX_Vect3AToB(dyn->m_BaseFloatationOmg_Dir, basevdir);
		omg1[0] = basevdir[0];
		omg1[1] = basevdir[1];
		omg1[2] = basevdir[2];
	}
	else
	{
		omg1[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][0];
		omg1[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][1];
		omg1[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial1][2];
	}
	
	Vect3 omg2;
	omg2[0] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][0];
	omg2[1] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][1];
	omg2[2] = dyn->m_JntRotAxisDir_inBase[AxisSerial2][2];
	Vect3 omgd;
	FX_VectCross(omg1, omg2, omgd);

	Vect3 F[8];
	Vect3 N[8];

	for (i = 0; i < dof; i++)
	{
		if (i < AxisSerial2)
		{
			F[i][0] = 0;
			F[i][1] = 0;
			F[i][2] = 0;

			N[i][0] = 0;
			N[i][1] = 0;
			N[i][2] = 0;
		}
		else
		{
			Vect3 _to_mcp;
			_to_mcp[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[AxisSerial2][0][3]);
			_to_mcp[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[AxisSerial2][1][3]);
			_to_mcp[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[AxisSerial2][2][3]);
			Vect3 acc;
			FX_VectCross(omgd, _to_mcp, acc);


			Vect3 a1;
			Vect3 a;

			FX_VectCross(omg1, _to_mcp, a1);
			FX_VectCross(omg2, a1, a);
			FX_VectAddToA(acc, a);
			FX_VectCross(omg2, _to_mcp, a1);
			FX_VectCross(omg1, a1, a);
			FX_VectAddToA(acc, a);

			F[i][0] = (acc[0]) * dyn->m_JntMass[i];
			F[i][1] = (acc[1]) * dyn->m_JntMass[i];
			F[i][2] = (acc[2]) * dyn->m_JntMass[i];



			FX_MMV3(dyn->m_JntInertia_inBase[i], omgd, N[i]);
			Vect3 t_t;
			Vect3 t;
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg1, t_t);
			FX_VectCross(omg2, t_t, t);
			FX_VectAddToA(N[i], t);
			FX_MMV3(dyn->m_JntInertia_inBase[i], omg2, t_t);
			FX_VectCross(omg1, t_t, t);
			FX_VectAddToA(N[i], t);
		}
	}

	Vect3 F_Tool;
	Vect3 N_Tool;
	{
		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		Vect3 a1;
		Vect3 a;
		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		FX_VectAddToA(acc, a);
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		FX_VectAddToA(acc, a);

		F_Tool[0] = (acc[0]) * dyn->m_ToolMass;
		F_Tool[1] = (acc[1]) * dyn->m_ToolMass;
		F_Tool[2] = (acc[2]) * dyn->m_ToolMass;

		FX_MMV3(dyn->m_ToolInertia_inBase, omgd, N_Tool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_ToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_ToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_Tool, t);
	}


	Vect3 F_NTool;
	Vect3 N_NTool;

	if (dyn->m_NToolTag == FX_TRUE)
	{

		Vect3 _to_mcp;
		_to_mcp[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_JointPG[AxisSerial2][0][3]);
		_to_mcp[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_JointPG[AxisSerial2][1][3]);
		_to_mcp[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_JointPG[AxisSerial2][2][3]);
		Vect3 acc;
		FX_VectCross(omgd, _to_mcp, acc);
		Vect3 a1;
		Vect3 a;
		FX_VectCross(omg1, _to_mcp, a1);
		FX_VectCross(omg2, a1, a);
		FX_VectAddToA(acc, a);
		FX_VectCross(omg2, _to_mcp, a1);
		FX_VectCross(omg1, a1, a);
		FX_VectAddToA(acc, a);

		F_NTool[0] = -(acc[0]) * dyn->m_NToolMass;
		F_NTool[1] = -(acc[1]) * dyn->m_NToolMass;
		F_NTool[2] = -(acc[2]) * dyn->m_NToolMass;

		FX_MMV3(dyn->m_NToolInertia_inBase, omgd, N_NTool);
		Vect3 t_t;
		Vect3 t;
		FX_MMV3(dyn->m_NToolInertia_inBase, omg1, t_t);
		FX_VectCross(omg2, t_t, t);
		FX_VectAddToA(N_Tool, t);
		FX_MMV3(dyn->m_NToolInertia_inBase, omg2, t_t);
		FX_VectCross(omg1, t_t, t);
		FX_VectAddToA(N_NTool, t);
	}

	Vect3 flange_f;
	{
		flange_f[0] = F_Tool[0];
		flange_f[1] = F_Tool[1];
		flange_f[2] = F_Tool[2];
		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_f, F_NTool);
		}
	}
	Vect3 flange_n;
	{
		flange_n[0] = N_Tool[0];
		flange_n[1] = N_Tool[1];
		flange_n[2] = N_Tool[2];

		Vect3 tool_mcp_2_flange_in_w;
		tool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_ToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
		tool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_ToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
		tool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_ToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

		Vect3 tool_lead_n;
		FX_VectCross(tool_mcp_2_flange_in_w, F_Tool, tool_lead_n);
		FX_VectAddToA(flange_n, tool_lead_n);

		if (dyn->m_NToolTag == FX_TRUE)
		{
			FX_VectAddToA(flange_n, N_NTool);

			Vect3 ntool_mcp_2_flange_in_w;
			ntool_mcp_2_flange_in_w[0] = 0.001 * (dyn->m_NToolMCP_inBase[0] - kine->m_FlangeTip[0][3]);
			ntool_mcp_2_flange_in_w[1] = 0.001 * (dyn->m_NToolMCP_inBase[1] - kine->m_FlangeTip[1][3]);
			ntool_mcp_2_flange_in_w[2] = 0.001 * (dyn->m_NToolMCP_inBase[2] - kine->m_FlangeTip[2][3]);

			Vect3 ntool_lead_n;
			FX_VectCross(ntool_mcp_2_flange_in_w, F_NTool, ntool_lead_n);
			FX_VectAddToA(flange_n, ntool_lead_n);
		}
	}

	for (i = Fdof; i >= 0; i--)
	{
		if (i == Fdof)
		{
			FX_VectAdd(F[i], flange_f, dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], flange_n, dyn->m_Link_N_inBase[i]);
			Vect3 to_mcp_v;
			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_FlangeTip[0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_FlangeTip[1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_FlangeTip[2][3] - kine->m_JointPG[i][2][3]);
			to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
			to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
			to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);

			Vect3 n_mcp;
			Vect3 n_nxt;

			FX_VectCross(to_mcp_v, F[i], n_mcp);
			FX_VectCross(to_nxt_v, flange_f, n_nxt);

			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);

		}
		else
		{
			FX_VectAdd(F[i], dyn->m_Link_F_inBase[i + 1], dyn->m_Link_F_inBase[i]);
			FX_VectAdd(N[i], dyn->m_Link_N_inBase[i + 1], dyn->m_Link_N_inBase[i]);

			Vect3 to_nxt_v;
			to_nxt_v[0] = 0.001 * (kine->m_JointPG[i + 1][0][3] - kine->m_JointPG[i][0][3]);
			to_nxt_v[1] = 0.001 * (kine->m_JointPG[i + 1][1][3] - kine->m_JointPG[i][1][3]);
			to_nxt_v[2] = 0.001 * (kine->m_JointPG[i + 1][2][3] - kine->m_JointPG[i][2][3]);
			Vect3 n_nxt;
			FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[i + 1], n_nxt);
			FX_VectAddToA(dyn->m_Link_N_inBase[i], n_nxt);
			if (i >= AxisSerial2)
			{
				Vect3 to_mcp_v;
				to_mcp_v[0] = 0.001 * (dyn->m_JntMCP_inBase[i][0] - kine->m_JointPG[i][0][3]);
				to_mcp_v[1] = 0.001 * (dyn->m_JntMCP_inBase[i][1] - kine->m_JointPG[i][1][3]);
				to_mcp_v[2] = 0.001 * (dyn->m_JntMCP_inBase[i][2] - kine->m_JointPG[i][2][3]);
				Vect3 n_mcp;
				FX_VectCross(to_mcp_v, F[i], n_mcp);
				FX_VectAddToA(dyn->m_Link_N_inBase[i], n_mcp);
			}
		}

		ret_Tau[i+1] = kine->m_JointPG[i][0][2] * dyn->m_Link_N_inBase[i][0]
			+ kine->m_JointPG[i][1][2] * dyn->m_Link_N_inBase[i][1]
			+ kine->m_JointPG[i][2][2] * dyn->m_Link_N_inBase[i][2];

	}

	{
		Vect3 to_nxt_v;
		to_nxt_v[0] = 0.001 * (kine->m_JointPG[0][0][3]);
		to_nxt_v[1] = 0.001 * (kine->m_JointPG[0][1][3]);
		to_nxt_v[2] = 0.001 * (kine->m_JointPG[0][2][3]);
		Vect3 n_nxt;
		FX_VectCross(to_nxt_v, dyn->m_Link_F_inBase[0], n_nxt);
		FX_VectAddToA(dyn->m_Link_N_inBase[0], n_nxt);

		Vect3 basevdir;
		FX_Vect3AToB(dyn->m_BaseFloatationOmg_Dir, basevdir);

		ret_Tau[0] = basevdir[0] * n_nxt[0]
			+ basevdir[1] * n_nxt[1]
			+ basevdir[2] * n_nxt[2];
	}
	return FX_TRUE;
}
FX_BOOL  FX_Robot_Dyna_Coriolis_Base_Flt(FX_INT32L RobotSerial, Matrix8 ret_ColiosBase[8])
{
	{
		if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
		{
			return FX_FALSE;
		}
		FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
		FX_DynBase* dyn = &pRobot->m_DynaBase;
		FX_KineBase* kine = &pRobot->m_KineBase;
		FX_INT32L dof = pRobot->m_RobotDOF;
		FX_INT32L i, j, k;
		FX_DOUBLE tau[8] = { 0 };
		for (i = -1; i < dof; i++) {

			for (j = i + 1; j < dof; j++)
			{
				FX_Robot_CalDualOmg_Flt(RobotSerial, i, j, tau);
				for (k = 0; k < dof+1; k++)
				{
					ret_ColiosBase[i+1][j+1][k] = tau[k] * 0.5;
				}
			}

		}
		return FX_TRUE;
	}
}


FX_BOOL  FX_Robot_Dyna_Coriolis_Mat_Flt(FX_INT32L RobotSerial, Matrix8 in_ColiosBase[8], Vect7 in_AngVel, Matrix8 ret_ColiosMat)
{
	if (RobotSerial < 0 || RobotSerial >= MAX_RUN_ROBOT_NUM)
	{
		return FX_FALSE;
	}
	FX_Robot* pRobot = (FX_Robot*)&m_Robot[RobotSerial];
	FX_DynBase* dyn = &pRobot->m_DynaBase;
	FX_KineBase* kine = &pRobot->m_KineBase;
	FX_INT32L dof = pRobot->m_RobotDOF;
	FX_INT32L i, j, k;
	FX_DOUBLE qd[8] = { 0 };
	
    qd[0] = dyn->m_BaseFloatationOmg_Val * FXARM_D2R;
	for (i = 0; i < dof; i++)
	{
		qd[i+1] = in_AngVel[i] * FXARM_D2R;
	}

	for (i = 0; i <= dof; i++)
	{
		for (j = 0; j <= dof; j++)
		{
			ret_ColiosMat[i][j] = 0;
		}
	}

	for (i = 0; i <= dof; i++) {

		for (j = i + 1; j <= dof; j++)
		{
			for (k = 0; k <= dof; k++)
			{
				ret_ColiosMat[k][i] += in_ColiosBase[i][j][k] * qd[j];
				ret_ColiosMat[k][j] += in_ColiosBase[i][j][k] * qd[i];
			}
		}
	}
	return FX_TRUE;
}
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

double dot(Vect3 a, Vect3 b)
{
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}


// double signed_angle_axis(
//     const double a[3],
//     const double b[3],
//     const double axis[3]   // 方向轴，例如 Vz2b
// ){
//     // dot
//     double dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2];

//     // cross = a × b
//     double cross[3] = {
//         a[1]*b[2] - a[2]*b[1],
//         a[2]*b[0] - a[0]*b[2],
//         a[0]*b[1] - a[1]*b[0]
//     };

//     // norms
//     double a_norm = FX_Sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2]);
//     double b_norm = FX_Sqrt(b[0]*b[0] + b[1]*b[1] + b[2]*b[2]);

//     // unsigned angle
//     double c = dot / (a_norm * b_norm);
//     if (c > 1.0) c = 1.0;
//     if (c < -1.0) c = -1.0;
//     double angle = FX_COS_ARC(c);

//     // sign = (cross · axis >= 0 ? +1 : -1)
//     double s = cross[0]*axis[0] + cross[1]*axis[1] + cross[2]*axis[2];
//     double sign = (s >= 0) ? 1.0 : -1.0;

//     return angle * sign;
// }